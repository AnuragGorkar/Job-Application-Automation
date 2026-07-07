import httpx
import logging
from typing import Optional

from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class NullScraper(BaseScraper):
    async def fetch(self, company_name: str, client: httpx.AsyncClient) -> list[ScrapedJob]:
        logger.debug("Ignoring company %s because no scraper is configured", company_name)
        return []
    
    def map_to_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:
        pass