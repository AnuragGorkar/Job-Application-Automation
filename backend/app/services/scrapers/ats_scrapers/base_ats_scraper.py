import asyncio
import logging
import random
from abc import abstractmethod
from typing import Optional

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
    def map_to_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:
        pass


    async def fetch(self, company_name: str) -> list[ScrapedJob]:
        url = self.build_company_url(company_name)
        jobs = []
        
        max_retries = 3
        base_delay = 2.0 
        
        for attempt in range(max_retries):
            current_timeout = httpx.Timeout(12.0 + (attempt * 10.0), connect=5.0)
            
            try:
                async with httpx.AsyncClient() as client:
                    r = await client.get(url, timeout=current_timeout)
                
                if r.status_code == 200:
                    data = r.json()
                    raw_jobs = data if isinstance(data, list) else data.get("jobs", [])
                    
                    for job in raw_jobs:
                        try:
                            scraped_job = self.map_to_scraped_job(job, company_name)
                            if scraped_job:
                                jobs.append(scraped_job)
                        except Exception as map_err:
                            logger.warning(f"Map error for {company_name}: {map_err}")
                    return jobs 
                    
                elif r.status_code in [429, 500, 502, 503, 504]:
                    logger.warning(f"Rate limit/Server error {r.status_code} for {company_name}. Retrying...")
                else:
                    logger.error(f"Permanent failure status {r.status_code} for {company_name}.")
                    return []

            except (httpx.ReadTimeout, httpx.ConnectTimeout) as t_err:
                logger.warning(f"Timeout on attempt {attempt + 1} for {company_name}: {t_err}")
            except httpx.RequestError as req_err:
                logger.error(f"Network request error for {company_name}: {req_err}")
                return []

            if attempt < max_retries - 1:
                delay = (base_delay * (2 ** attempt)) * random.uniform(0.5, 1.5)
                logger.info(f"Backing off for {delay:.2f} seconds before retrying {company_name}...")
                await asyncio.sleep(delay)

        logger.error(f"All {max_retries} retry attempts failed for {company_name}.")
        return []