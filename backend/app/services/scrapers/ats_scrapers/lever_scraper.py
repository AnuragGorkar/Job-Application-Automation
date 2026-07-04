from datetime import datetime, timezone
from typing import Final

from app.schemas.scraped_job import ScrapedJob
from app.services.scrapers.ats_scrapers.base_ats_scraper import BaseATSScraper


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