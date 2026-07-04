import logging
from abc import abstractmethod

import httpx

from app.schemas.scraped_job import ScrapedJob
from app.services.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class BaseATSScraper(BaseScraper):
    def __init__(self, base_url, params):
        self.base_url = base_url
        self.params = params

    def build_company_url(self, company_name: str) -> str:
        company_url = self.base_url + company_name
        url_params = "?"
        for key, value in self.params.items():
            url_params += key + "=" + value
        
        return company_url + url_params
    
    @abstractmethod
    def map_to_scraped_job(self, job: dict, company_name: str) -> ScrapedJob:
        pass
    
    async def fetch(self, company_name: str) -> list[ScrapedJob]:
        url = self.build_company_url(company_name)
        jobs = []
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, timeout=8.0)

            if r.status_code == 200:
                logger.debug("Fetched %s jobs for %s from %s", len(r.json().get("jobs", [])), company_name, url)
                for job in r.json().get("jobs", []):
                    scraped_job = self.map_to_scraped_job(job, company_name)
                    jobs.append(scraped_job)
            else:
                logger.warning("Received status %s while scraping %s", r.status_code, company_name)

        except Exception as exc:
            logger.exception("Exception while scraping jobs for %s: %s", company_name, exc)

        return jobs