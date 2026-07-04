import asyncio
from app.schemas.scraped_job import ScrapedJob
from app.services.scrapers.scraper_factory import ScraperFactory
from app.services.scrapers.validators.validations_builder import ValidationsBuilder

class JobScraper:
    def __init__(self, companies_dict: dict[str, list[str]]):
        self.validator = ValidationsBuilder.get_all_validations()
        self.companies_dict = companies_dict
        self.scraper_dict = {}
        self.build_scraper_dict(companies_dict) # Fixed: properly populate dict
        
        self.job_queue = asyncio.Queue()
        self.valid_jobs = []
    
    def build_scraper_dict(self, companies_dict: dict[str, list[str]]):
        for scraper in companies_dict.keys():
            self.scraper_dict[scraper] = ScraperFactory.get_scraper(scraper)

    async def _company_scraper(self, platform_name: str, company_name: str):
        scraper = self.scraper_dict.get(platform_name)
        if not scraper:
            return

        try:
            jobs = await scraper.fetch(company_name) 
            if jobs:
                await self.job_queue.put(jobs)
        except Exception as e:
            print(f"[Async Error] Platform {platform_name}, company {company_name} failed: {e}")

    async def _validation_job(self):
        while True:
            job_batch = await self.job_queue.get()
            
            if job_batch is None:
                self.job_queue.task_done()
                break
            
            try:
                for job in job_batch:
                    if self.validator.validate(job):
                        self.valid_jobs.append(job)
            except Exception as e:
                print(f"Job validation error in queue: {e}")
            finally:
                self.job_queue.task_done()

    async def scrape_and_validate(self) -> list[ScrapedJob]:
        self.valid_jobs = [] 
        
        # Start background consumer task
        consumer_task = asyncio.create_task(self._validation_job())

        # Flatten targets
        tasks = [
            self._company_scraper(platform, company)
            for platform, companies in self.companies_dict.items()
            for company in companies
        ]

        # Run all scrapers concurrently
        await asyncio.gather(*tasks)

        # Signal consumer to stop
        await self.job_queue.put(None)
        
        # Wait for consumer to finish processing
        await consumer_task

        print(f"[Complete] Validation finished. Returning {len(self.valid_jobs)} matching jobs.")
        return self.valid_jobs