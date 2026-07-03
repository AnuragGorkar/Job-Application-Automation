from typing import Final
import datetime, timezone

from app.service.scrapers.base_ats_scraper import BaseATSScraper
from app.schemas.job import ScrapedJob

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


class LeverScraper(BaseATSScraper):
    _instance = None

    BASE_URL: Final[str] = "https://api.lever.co/v0/postings/"
    PARAMS: Final[dict] = {
        "mode" : "json"
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
        created_at = job.get('createdAt')
        iso_time = datetime.fromtimestamp(created_at / 1000.0, tz=timezone.utc).isoformat() if created_at else None

        scraped_job = ScrapedJob(
                        title=job.get('text'),
                        location=job.get('categories', {}).get('location', 'Unknown'),
                        posted_at=iso_time,
                        url=job.get('hostedUrl'),
                        company=company_name,
                        platform="Lever"
                    )

        return scraped_job

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