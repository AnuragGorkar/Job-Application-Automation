import asyncio
import logging
import random
from asyncio import Queue
from datetime import datetime
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from aiolimiter import AsyncLimiter

from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.base_scraper import BaseScraper
from app.services.job_scrapers.scraper_config import ScraperConfig
from app.utils.html_utils import clean_html

logger = logging.getLogger(__name__)

AMAZON_JOBS_URL = "https://www.amazon.jobs/en-gb/search?offset=0&result_limit=10&sort=recent&category%5B%5D=software-development&job_type%5B%5D=Full-Time&country%5B%5D=USA"

class AmazonScraper(BaseScraper):
    def __init__(self, validation_queue: Queue, enrichment_queue: Queue, batch_limit: int = 100, max_concurrency: int = 5, config: ScraperConfig | None = None):
        super().__init__(
            validation_queue=validation_queue,
            enrichment_queue=enrichment_queue, 
            config=config
        )
        self.company_name = "Amazon"
        self.parsed_url = urlparse(AMAZON_JOBS_URL.replace("/search?", "/search.json?"))
        self.query_params = parse_qs(self.parsed_url.query)

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Encoding": "gzip, deflate"
        }

        self.batch_limit = batch_limit
        self.max_concurrency = max_concurrency

    def _build_query_url(self, limit: int, offset: int) -> str:
        params = dict(self.query_params)
        params["result_limit"] = [str(limit)]
        params["offset"] = [str(offset)]
        return urlunparse(self.parsed_url._replace(query=urlencode(params, doseq=True)))

    def map_to_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:
        posted_date_str = job.get("posted_date", "")
        try:
            posted_at = datetime.strptime(posted_date_str, "%B %d, %Y")
        except (ValueError, TypeError):
            posted_at = None

        title = job.get("title", "").strip()
        raw_location = job.get("location")
        location = raw_location if isinstance(raw_location, str) else job.get("city")

        job_id = str(job.get("id", ""))
        job_path = job.get("job_path", f"/jobs/{job_id}")
        url = f"https://www.amazon.jobs{job_path}"

        business_cat = job.get("business_category", "N/A")
        city = job.get("city", "N/A")

        raw_desc = f"Company: {company_name}\nCity: {city}\nBusiness Category: {business_cat}\n\n"
        raw_desc += f"### Description\n{job.get('description', '')}\n\n"
        if job.get("basic_qualifications"):
            raw_desc += f"### Basic Qualifications\n{job.get('basic_qualifications')}"

        description = clean_html(raw_desc)

        return ScrapedJob(
            title=title,
            location=location,
            description=description,
            posted_at=posted_at,
            url=url,
            company=company_name,
            platform=self.company_name,
        )

    async def _fetch_batch(self, offset: int, client: httpx.AsyncClient) -> tuple[list[ScrapedJob], int]:
        batch_url = self._build_query_url(self.batch_limit, offset)
        jobs: list[ScrapedJob] = []
        max_retries = self.config.max_retries

        for attempt in range(max_retries):
            timeout = httpx.Timeout(12.0 + attempt * 10.0, connect=5.0)
            try:
                response = await client.get(batch_url, headers=self.headers, timeout=timeout)
                response.raise_for_status()
                data = response.json()
                raw_jobs = data.get("jobs", [])
                total_hits = data.get("hits", 0)

                for raw_job in raw_jobs:
                    scraped_job = self.map_to_scraped_job(raw_job, self.company_name)
                    if scraped_job:
                        jobs.append(scraped_job)

                return jobs, total_hits

            except httpx.RequestError as request_err:
                logger.error("Network request error for AMAZON offset %s: %s", offset, request_err)
                break
            except Exception as exc:
                logger.exception("Failed mapping AMAZON batch at offset %s: %s", offset, exc)
                break

            if attempt < max_retries - 1:
                await asyncio.sleep((self.config.base_delay * (2 ** attempt)) * random.uniform(0.5, 1.5))

        return [], 0

    async def fetch(self, company_name: str, client: httpx.AsyncClient) -> int:
        queued_count = 0
        first_batch, total_hits = await self._fetch_batch(0, client)
        
        for job in first_batch:
            if job is not None:
                await self.validation_queue.put(job)
                queued_count += 1

        if total_hits == 0:
            return queued_count

        offsets = [offset for offset in range(self.batch_limit, total_hits, self.batch_limit)]
        semaphore = asyncio.Semaphore(self.max_concurrency or self.config.semaphore_value)

        async def bounded_fetch(offset: int) -> list[ScrapedJob]:
            async with semaphore:
                batch_jobs, _ = await self._fetch_batch(offset, client)
                return batch_jobs

        if offsets:
            batch_results = await asyncio.gather(*(bounded_fetch(offset) for offset in offsets))
            for batch in batch_results:
                for job in batch:
                    if job is not None:
                        await self.validation_queue.put(job)
                        queued_count += 1

        return queued_count

    async def enrich(self, company_name: str, job: ScrapedJob, client: Optional[httpx.AsyncClient] = None) -> ScrapedJob:
        # Amazon jobs are completely populated in Phase 1. Just pass it through.
        return job