from abc import ABC, abstractmethod
from app.schemas.scraped_job import ScrapedJob

class BaseScraper(ABC):
    @abstractmethod
    def fetch(self, client_name: str) -> list[ScrapedJob]:
        """Must return a list of ScrapedJob objects."""
        pass