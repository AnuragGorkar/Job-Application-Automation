from datetime import datetime, timezone
from typing import Final, Optional

from app.schemas.scraped_job import ScrapedJob
from app.services.scrapers.ats_scrapers.base_ats_scraper import BaseATSScraper


class LeverScraper(BaseATSScraper):
    BASE_URL: Final[str] = "https://api.lever.co/v0/postings/"
    PARAMS: Final[dict] = {
        "mode" : "json"
        }

    def __init__(self):
        super().__init__(
            base_url = self.BASE_URL, 
            params = self.PARAMS
        )
    
    # 3. LEVER SCRAPER
    def map_to_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:
        title = job.get('text')
        url = job.get('hostedUrl')
        
        categories = job.get('categories') or {}
        loc_name = categories.get('location')

        if not title or not url or not loc_name:
            return None

        created_at = job.get('createdAt')
        iso_time = datetime.fromtimestamp(created_at / 1000.0, tz=timezone.utc).isoformat() if created_at else None

        return ScrapedJob(
            title=title,
            location=loc_name,
            posted_at=iso_time,
            url=url,
            company=company_name,
            platform="Lever"
        )