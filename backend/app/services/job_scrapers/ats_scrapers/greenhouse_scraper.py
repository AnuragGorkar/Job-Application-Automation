import html
import logging

from bs4 import BeautifulSoup
from typing import Final, Optional
import datetime

from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.ats_scrapers.base_ats_scraper import BaseATSScraper


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
        # Add company name
        company_url = self.base_url + company_name + "/" + "jobs"

        # Add parameters
        url_params= "?"
        for key, value in self.params.items():
            url_params += key + "=" + value
        
        scrape_url = company_url + url_params

        return scrape_url
    
    def map_to_ats_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:
        title = job.get('title')
        url = job.get('absolute_url')
        
        loc_data = job.get('location') or {}
        loc_name = loc_data.get('name') if isinstance(loc_data, dict) else None

        raw_description = job.get('content', '')
        raw_description = html.unescape(raw_description)
        clean_description = BeautifulSoup(raw_description, 'html.parser').get_text(separator='\n').strip()
        posted_at = job.get('updated_at', None)
        
        if not title or not url or not loc_name or not clean_description or not posted_at:
            return None

        return ScrapedJob(
            title=title,
            description=clean_description,
            location=loc_name,
            posted_at=posted_at,
            url=url,
            company=company_name,
            platform="Greenhouse"
        )