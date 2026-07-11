import asyncio
import logging

import httpx

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
        self.build_scraper_dict(companies_dict)

        self.job_queue = asyncio.Queue()
        self.valid_jobs = []
        self.scraper_config = DEFAULT_SCRAPER_CONFIG

    def build_scraper_dict(self, companies_dict: dict[str, list[str]]):
        for scraper in companies_dict.keys():
            self.scraper_dict[scraper] = ScraperFactory.get_scraper(scraper, self.job_queue)

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
            job = await self.job_queue.get()

            if job is None:
                self.job_queue.task_done()
                break

            try:
                if self.validator.validate(job):
                    self.valid_jobs.append(job)
            except Exception as exc:
                logger.exception("Job validation error in queue: %s", exc)
            finally:
                self.job_queue.task_done()

    async def scrape_and_validate(self) -> list[ScrapedJob]:
        self.valid_jobs = []

        consumer_task = asyncio.create_task(self._validation_job())

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

        await self.job_queue.put(None)

        await consumer_task

        self.validator.log_validation_stats()
        logger.info("Validation finished. Returning %s matching jobs.", len(self.valid_jobs))
        return self.valid_jobs