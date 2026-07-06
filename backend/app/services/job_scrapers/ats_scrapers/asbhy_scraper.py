import html
import logging
from typing import Final, Optional
import datetime
from bs4 import BeautifulSoup

from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.ats_scrapers.base_ats_scraper import BaseATSScraper

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
    
    def map_to_ats_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:
        title = job.get('title')
        url = job.get('jobUrl')
        location = job.get('location')

        raw_description = job.get('description', '')
        raw_description = html.unescape(raw_description)
        clean_description = BeautifulSoup(raw_description, 'html.parser').get_text(separator='\n').strip()

        posted_at = job.get('publishedAt', None)
        
        if not title or not url or not location or not clean_description or not posted_at:
            return None

        return ScrapedJob(
            title=title,
            location=location,
            description=clean_description,
            posted_at=posted_at,
            url=url,
            company=company_name,
            platform="Ashby"
        )