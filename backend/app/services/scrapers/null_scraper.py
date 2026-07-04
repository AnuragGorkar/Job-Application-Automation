import logging

from app.schemas.scraped_job import ScrapedJob
from app.services.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class NullScraper(BaseScraper):
    def fetch(self, company_name: str) -> list[ScrapedJob]:
        logger.debug("Ignoring company %s because no scraper is configured", company_name)
        return []