import logging
from queue import Queue
from typing import Optional

import httpx

from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class NullScraper(BaseScraper):
    def __init__(self, job_queue: Queue):
        super().__init__(job_queue)
        
    async def fetch(self, company_name: str, client: httpx.AsyncClient) -> int:
        logger.debug("Ignoring company %s because no scraper is configured", company_name)
        return 0
    
    def map_to_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:
        return None