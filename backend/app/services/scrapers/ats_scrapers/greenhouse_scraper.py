from datetime import datetime, timezone
from typing import Final

from app.schemas.scraped_job import ScrapedJob
from app.services.scrapers.ats_scrapers.base_ats_scraper import BaseATSScraper


class GreenhouseScraper(BaseATSScraper):
    _instance = None

    BASE_URL: Final[str] = "https://boards-api.greenhouse.io/v1/boards/"
    PARAMS: Final[dict] = {
        "content" : "true"
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
    
    def build_company_url(self, company_name: str) -> str:
        # Add company name
        company_url = self.base_url + company_name + "/" + "jobs"

        # Add parameters
        url_params= "?"
        for key, value in self.params.items():
            url_params += key + "=" + value
        
        scrape_url = company_url + url_params

        return scrape_url
    
    def map_to_scraped_job(self, job: dict, company_name: str) -> ScrapedJob:
        scraped_job = ScrapedJob(
                        title=job.get('title'),
                        location=job.get('location', {}).get('name', 'Unknown'),
                        posted_at=job.get('updated_at'),
                        url=job.get('absolute_url'),
                        company=company_name,
                        platform="Greenhouse"
                    )

        return scraped_job