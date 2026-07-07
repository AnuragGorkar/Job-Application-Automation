from abc import ABC, abstractmethod
from typing import Optional

import httpx

from app.schemas.scraped_job import ScrapedJob

class BaseScraper(ABC):
    @abstractmethod
    async def fetch(self, company_name: str, client: httpx.AsyncClient) -> list[ScrapedJob]:
        """Must return a list of ScrapedJob objects."""
        pass

    @abstractmethod
    def map_to_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:
        pass