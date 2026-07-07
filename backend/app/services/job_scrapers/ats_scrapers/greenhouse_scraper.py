import logging
from typing import Final, Optional

from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.ats_scrapers.base_ats_scraper import BaseATSScraper
from app.utils.html_utils import clean_html


class GreenhouseScraper(BaseATSScraper):
    BASE_URL: Final[str] = "https://boards-api.greenhouse.io/v1/boards/"
    PARAMS: Final[dict] = {
        "content" : "true"
        }

    def __init__(self):
        super().__init__(
            base_url = self.BASE_URL, 
            params = self.PARAMS
        )
    
    def build_company_url(self, company_name: str) -> str:
        return self.base_url + company_name + "/jobs"
    
    def map_to_ats_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:
        title = job.get('title')
        url = job.get('absolute_url')
        
        loc_data = job.get('location') or {}
        loc_name = loc_data.get('name') if isinstance(loc_data, dict) else None

        clean_description = clean_html(job.get('content', ''))
        posted_at = job.get('updated_at', None)

        return ScrapedJob(
            title=title,
            description=clean_description,
            location=loc_name,
            posted_at=posted_at,
            url=url,
            company=company_name,
            platform="Greenhouse"
        )