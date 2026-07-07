import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.base_scraper import BaseScraper
from app.utils.html_utils import clean_html

logger = logging.getLogger(__name__)

AMAZON_JOBS_URL = "https://www.amazon.jobs/en-gb/search?offset=0&result_limit=10&sort=recent&category%5B%5D=software-development&job_type%5B%5D=Full-Time&country%5B%5D=USA"


class AmazonScraper(BaseScraper):
    def __init__(self, batch_limit: int = 100, max_concurrency: int = 5):
        self.company_name = "Amazon"
        self.parsed_url = urlparse(AMAZON_JOBS_URL.replace("/search?", "/search.json?"))
        self.query_params = parse_qs(self.parsed_url.query)

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
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
            logger.debug("Failed to parse posted_date '%s' for AMAZON job: %s", posted_date_str, job)
            posted_at = None

        title = job.get("title", "").strip()
        raw_location = job.get("location")
        location = raw_location if isinstance(raw_location, str) else job.get("city")

        job_id = str(job.get("id", ""))
        job_path = job.get("job_path", f"/jobs/{job_id}")
        url = f"https://www.amazon.jobs{job_path}"

        business_cat = job.get("business_category", "N/A")
        city = job.get("city", "N/A")

        raw_desc = f"Company: {company_name}\n"
        raw_desc += f"City: {city}\n"
        raw_desc += f"Business Category: {business_cat}\n\n"
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
        """Fetches a batch and returns both the parsed jobs AND the total hits count."""
        batch_url = self._build_query_url(self.batch_limit, offset)
        jobs: list[ScrapedJob] = []

        max_retries = 3
        base_delay = 2.0

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

            except (httpx.ReadTimeout, httpx.ConnectTimeout) as timeout_err:
                logger.warning("Timeout on attempt %s for AMAZON offset %s: %s", attempt + 1, offset, timeout_err)
            except httpx.RequestError as request_err:
                logger.error("Network request error for AMAZON offset %s: %s", offset, request_err)
                break  # Don't retry on fatal bad requests (like 404 or invalid params)
            except Exception as exc:
                logger.exception("Failed mapping AMAZON batch at offset %s: %s", offset, exc)
                break

            # Retries only execute if we hit a recoverable exception (like a timeout)
            if attempt < max_retries - 1:
                delay = (base_delay * (2 ** attempt)) * random.uniform(0.5, 1.5)
                await asyncio.sleep(delay)

        logger.error("All %s retry attempts failed or aborted for AMAZON offset %s.", max_retries, offset)
        return [], 0

    async def fetch(self, company_name: str, client: httpx.AsyncClient) -> list[ScrapedJob]:
        jobs: list[ScrapedJob] = []
        first_offset = 0

        # Extract total hits right from the first call to save a network request
        first_batch, total_hits = await self._fetch_batch(first_offset, client)
        jobs.extend(first_batch)

        if total_hits == 0:
            return jobs

        offsets = [offset for offset in range(self.batch_limit, total_hits, self.batch_limit)]
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def bounded_fetch(offset: int) -> list[ScrapedJob]:
            async with semaphore:
                batch_jobs, _ = await self._fetch_batch(offset, client)
                return batch_jobs

        if offsets:
            batch_results = await asyncio.gather(*(bounded_fetch(offset) for offset in offsets))
            for batch in batch_results:
                jobs.extend(batch)

        return jobs