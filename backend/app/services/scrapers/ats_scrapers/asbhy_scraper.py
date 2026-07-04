from typing import Final

from app.schemas.scraped_job import ScrapedJob
from app.services.scrapers.ats_scrapers.base_ats_scraper import BaseATSScraper

class AshbyScraper(BaseATSScraper):
    _instance = None

    BASE_URL: Final[str] = "https://api.ashbyhq.com/posting-api/job-board/"
    PARAMS: Final[dict] = {
        "includeCompensation" : "true"
        }

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            # Singleton pattern
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        super().__init__(
            base_url = self.BASE_URL, 
            params = self.PARAMS
        )
    
    def map_to_scraped_job(self, job: dict, company_name: str) -> ScrapedJob:
        scraped_job = ScrapedJob(
                        title=job.get('title'),
                        location=job.get('location', 'Unknown'),
                        posted_at=job.get('publishedAt'),
                        url=job.get('jobUrl'),
                        company=company_name,
                        platform="Ashby"
                    )
        return scraped_job