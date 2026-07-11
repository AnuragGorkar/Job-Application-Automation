from abc import ABC, abstractmethod
from asyncio import Queue
from typing import Optional

import httpx

from app.schemas.scraped_job import ScrapedJob

class BaseScraper(ABC):
    def __init__(self, job_queue: Queue):
        self.job_queue = job_queue

    @abstractmethod
    async def fetch(self, company_name: str, client: httpx.AsyncClient) -> int:
        """Push ScrapedJob objects into the shared job queue and return the number of jobs queued."""
        pass

    @abstractmethod
    def map_to_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:
        pass