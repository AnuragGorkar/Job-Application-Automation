from typing import Final, Optional

from app.schemas.scraped_job import ScrapedJob
from app.services.scrapers.ats_scrapers.base_ats_scraper import BaseATSScraper

class AshbyScraper(BaseATSScraper):
    BASE_URL: Final[str] = "https://api.ashbyhq.com/posting-api/job-board/"
    PARAMS: Final[dict] = {
        "includeCompensation" : "true"
        }
    
    def __init__(self):
        super().__init__(
            base_url = self.BASE_URL, 
            params = self.PARAMS
        )
    
    def map_to_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:
        title = job.get('title')
        url = job.get('jobUrl')
        location = job.get('location')

        if not title or not url or not location:
            return None

        return ScrapedJob(
            title=title,
            location=location,
            posted_at=job.get('publishedAt'),
            url=url,
            company=company_name,
            platform="Ashby"
        )