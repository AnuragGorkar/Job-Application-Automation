from app.schemas.scraped_job import ScrapedJob
from app.services.scrapers.base_scraper import BaseScraper


class NullScraper(BaseScraper):
    def fetch(self, company_name: str) -> list[ScrapedJob]:
        # Does nothing. Safely returns empty list.
        print(f"[NullScraper] Ignored company: {company_name}")
        return []