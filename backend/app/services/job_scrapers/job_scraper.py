import asyncio
import logging
import httpx
import time

from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.scraper_config import DEFAULT_SCRAPER_CONFIG
from app.services.job_scrapers.scraper_factory import ScraperFactory
from app.services.job_scrapers.validators.validations_builder import ValidationsBuilder

logger = logging.getLogger(__name__)

class JobScraper:
    def __init__(self, companies_dict: dict[str, list[str]]):
        logger.info("Initializing JobScraper with %s platforms", len(companies_dict))

        self.validator = ValidationsBuilder.get_all_validations()
        self.companies_dict = companies_dict
        self.scraper_dict = {}

        self.validation_queue = asyncio.Queue()
        self.enrichment_queue = asyncio.Queue()

        self.build_scraper_dict(companies_dict)

        self.valid_jobs = []
        self.scraper_config = DEFAULT_SCRAPER_CONFIG

    def build_scraper_dict(self, companies_dict: dict[str, list[str]]):
        for scraper in companies_dict.keys():
            self.scraper_dict[scraper] = ScraperFactory.get_scraper(scraper, self.validation_queue, self.enrichment_queue)

    async def _company_scraper(self, platform_name: str, company_name: str, client: httpx.AsyncClient):
        scraper = self.scraper_dict.get(platform_name)
        if not scraper:
            logger.debug("No scraper configured for platform %s", platform_name)
            return

        try:
            logger.debug("Starting scrape for %s on %s", company_name, platform_name)
            job_count = await scraper.fetch(company_name, client)
            logger.info("Completed scrape for %s on %s with %s jobs queued", company_name, platform_name, job_count)
        except Exception as exc:
            logger.exception("Scrape failed for %s on %s: %s", company_name, platform_name, exc)

    async def _validation_job(self):
        while True:
            job = await self.validation_queue.get()
  
            try:
                if self.validator.validate(job):
                    logger.info(f"Jobs validated now starting enrichment {job.platform} {job.company}")
                    await self.enrichment_queue.put((job.platform, job.company, job))
            except Exception as exc:
                logger.exception("Job validation error in queue: %s", exc)
            finally:
                self.validation_queue.task_done()
    
    async def _enrichment_job(self):
        while True:
            platform_name, company_name, job = await self.enrichment_queue.get()

            try:
                scraper = self.scraper_dict.get(platform_name)
                if not scraper:
                    logger.debug("No scraper configured for platform %s", platform_name)
                    continue 

                logger.debug("Starting enrichment for %s on %s", company_name, platform_name)
                enriched_job = await scraper.enrich(company_name=company_name, client=None, job=job) 
                logger.info("Completed enrichment for %s on %s", company_name, platform_name)
                                
                self.valid_jobs.append(enriched_job)
            except Exception as exc:
                logger.exception("Job enrichment error in queue: %s", exc)
            finally:
                self.enrichment_queue.task_done()

    async def scrape_and_validate(self) -> list[ScrapedJob]:
        self.valid_jobs = []

        # Spin up a single validation worker in the background
        validation_tasks = [asyncio.create_task(self._validation_job())  for _ in range(10)]
        
        # Spin up MULTIPLE enrichment workers (e.g., 10) to process network requests concurrently
        enrichment_tasks = [asyncio.create_task(self._enrichment_job()) for _ in range(10)]

        start_time = time.time()

        limits = httpx.Limits(
            max_connections=self.scraper_config.http_limits_max_connections,
            max_keepalive_connections=self.scraper_config.http_limits_max_keepalive_connections,
        )
        async with httpx.AsyncClient(limits=limits) as client:
            tasks = [
                self._company_scraper(platform, company, client)
                for platform, companies in self.companies_dict.items()
                for company in companies
            ]

            await asyncio.gather(*tasks)

        # Wait for both queues to be completely processed
        await self.validation_queue.join()
        await self.enrichment_queue.join()

        # Cancel all infinite background tasks so the script can exit cleanly
        for task in validation_tasks:
            task.cancel()
        for task in enrichment_tasks:
            task.cancel()

        self.validator.log_validation_stats()
        logger.info("Validation finished. Returning %s matching jobs.", len(self.valid_jobs))
        
        time_taken = time.time() - start_time
        logger.info(f"Time taken: {time_taken//60}m {time_taken%60}sec")
        return self.valid_jobs