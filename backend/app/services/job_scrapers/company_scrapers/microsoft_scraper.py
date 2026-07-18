import asyncio
import logging
import random
from datetime import datetime
from queue import Queue
from typing import Optional
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup
from aiolimiter import AsyncLimiter

from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.base_scraper import BaseScraper
from app.services.job_scrapers.scraper_config import ScraperConfig

logger = logging.getLogger(__name__)

class MicrosoftScraper(BaseScraper):
    def __init__(self, validation_queue: Queue, enrichment_queue: Queue, max_concurrency: int = 5, config: ScraperConfig | None = None):
        super().__init__(
            validation_queue=validation_queue,
            enrichment_queue=enrichment_queue, 
            config=config
            )
        self.company_name = "microsoft"
        self.frontend_urls = [
            "https://apply.careers.microsoft.com/careers?query=Software+Engineer&start=30&location=Seattle%2C++WA%2C++United+States&pid=1970393556883703&sort_by=timestamp&filter_distance=160&filter_include_remote=1&filter_career_discipline=Software+Engineering%2CData+Science&filter_profession=software+engineering&filter_seniority=Entry%2CMid-Level",
            "https://apply.careers.microsoft.com/careers?query=Software+Engineer&start=0&location=Sunnyvale%2C++CA%2C++United+States&pid=1970393556918542&sort_by=relevance&filter_distance=160&filter_include_remote=1&filter_career_discipline=Software+Engineering%2CData+Science&filter_profession=software+engineering&filter_seniority=Entry%2CMid-Level",
            "https://apply.careers.microsoft.com/careers?query=Software+Engineer&start=0&location=Mountain+View%2C++CA%2C++United+States&pid=1970393556849595&sort_by=relevance&filter_distance=160&filter_include_remote=1&filter_career_discipline=Software+Engineering%2CData+Science&filter_profession=software+engineering&filter_seniority=Entry%2CMid-Level",
            "https://apply.careers.microsoft.com/careers?query=Software+Engineer&start=0&location=New+York%2C++NY%2C++United+States&pid=1970393556849595&sort_by=relevance&filter_distance=160&filter_include_remote=1&filter_career_discipline=Software+Engineering%2CData+Science&filter_profession=software+engineering&filter_seniority=Entry%2CMid-Level",
            "https://apply.careers.microsoft.com/careers?query=Software+Engineer&start=0&location=Austin%2C++TX%2C++United+States&pid=1970393556918542&sort_by=relevance&filter_distance=160&filter_include_remote=1&filter_career_discipline=Software+Engineering%2CData+Science&filter_profession=software+engineering&filter_seniority=Entry%2CMid-Level",
            "https://apply.careers.microsoft.com/careers?query=Software+Engineer&start=0&location=San+Francisco%2C++CA%2C++United+States&pid=1970393556849595&sort_by=relevance&filter_distance=160&filter_include_remote=1&filter_career_discipline=Software+Engineering%2CData+Science&filter_profession=software+engineering&filter_seniority=Entry%2CMid-Level"
        ]
        self.max_concurrency = max_concurrency
        
        self.search_api_url = "https://apply.careers.microsoft.com/api/pcsx/search"
        self.details_api_url = "https://apply.careers.microsoft.com/api/pcsx/position_details"

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate"
        }

        self.rate_limiter = AsyncLimiter(max_rate=5, time_period=1)

    def _parse_url_to_api_params(self, url: str) -> dict:
        parsed_url = urlparse(url)
        raw_params = parse_qs(parsed_url.query)
        params = {}
        for key, val_list in raw_params.items():
            processed_vals = []
            for val in val_list:
                if key.startswith("filter_") and "," in val:
                    processed_vals.extend([v.strip() for v in val.split(",")])
                else:
                    processed_vals.append(val)
            params[key] = processed_vals

        params["domain"] = ["microsoft.com"]
        if "pid" in params:
            del params["pid"]
        return params

    def map_to_scraped_job(self, pos: dict, company_name: str) -> ScrapedJob:
        title = pos.get("name", "").strip()
        job_id = str(pos.get("id", ""))

        loc_list = pos.get("locations", [])
        location = loc_list[0] if loc_list else "USA"
        
        # Initial description just holds basic stats so it doesn't fail basic validations
        custom_desc = f"Company: {company_name}\nLocations: {' | '.join(loc_list)}\n"
        
        raw_ts = pos.get("postedTs")
        try:
            posted_at = datetime.utcfromtimestamp(float(raw_ts)) if raw_ts else datetime.now()
        except (ValueError, TypeError):
            posted_at = datetime.now()

        url = pos.get("publicUrl", f"https://apply.careers.microsoft.com/careers/job/{job_id}")

        return ScrapedJob(
            title=title,
            location=location,
            description=custom_desc.strip(),
            posted_at=posted_at,
            url=url,
            company=company_name,
            platform=self.company_name,
        )

    async def _fetch_search_batch(self, base_params: dict, offset: int, client: httpx.AsyncClient, company_name: str) -> tuple[list[ScrapedJob], int]:
        params = dict(base_params)
        params["start"] = [str(offset)]

        try:
            response = await client.get(self.search_api_url, params=params, timeout=10.0, headers=self.headers)
            response.raise_for_status()
            data = response.json().get("data", {})

            positions = data.get("positions", [])
            total_hits = data.get("count", 0)
            
            summary_jobs = [self.map_to_scraped_job(pos, company_name) for pos in positions if pos.get("id")]
            return summary_jobs, total_hits
        except Exception as exc:
            logger.error("Failed executing search batch at offset %s: %s", offset, exc)
            return [], 0

    async def _gather_jobs_for_url(self, url: str, client: httpx.AsyncClient, company_name: str, semaphore: asyncio.Semaphore) -> int:
        base_params = self._parse_url_to_api_params(url)
        queued_count = 0

        first_batch, total_hits = await self._fetch_search_batch(base_params, 0, client, company_name)
        for job in first_batch:
            await self.validation_queue.put(job)
            queued_count += 1

        if total_hits == 0 or not first_batch:
            return queued_count

        page_size = len(first_batch) or 20
        offsets = [offset for offset in range(page_size, total_hits, page_size)]

        async def bounded_search_fetch(offset: int):
            async with semaphore:
                batch_jobs, _ = await self._fetch_search_batch(base_params, offset, client, company_name)
                return batch_jobs

        if offsets:
            batch_results = await asyncio.gather(*(bounded_search_fetch(offset) for offset in offsets))
            for batch in batch_results:
                for job in batch:
                    await self.validation_queue.put(job)
                    queued_count += 1

        return queued_count

    async def fetch(self, company_name: str, client: httpx.AsyncClient) -> int:
        logger.info("Executing Phase 1: Gathering Microsoft Summary Jobs...")
        semaphore = asyncio.Semaphore(self.max_concurrency or self.config.semaphore_value)
        
        search_tasks = [self._gather_jobs_for_url(url, client, company_name, semaphore) for url in self.frontend_urls]
        results = await asyncio.gather(*search_tasks)
        
        total_queued = sum(results)
        logger.info("Phase 1 Complete. Pushed %s summary Microsoft jobs to validation queue.", total_queued)
        return total_queued

    async def enrich(self, company_name: str, job: ScrapedJob, client: Optional[httpx.AsyncClient] = None) -> ScrapedJob:
        job_id = job.url.split('/')[-1]
        detail_params = {"position_id": job_id, "domain": "microsoft.com", "hl": "en"}
        
        close_client = False
        if not client:
            client = httpx.AsyncClient()
            close_client = True

        for attempt in range(self.config.max_retries):
            try:
                # <-- Wrap the actual HTTP network request inside the limiter
                async with self.rate_limiter:
                    response = await client.get(self.details_api_url, params=detail_params, timeout=12.0, headers=self.headers)
                
                # We still keep the 429 handler as a fallback just in case the API has stricter long-term limits
                if response.status_code == 429:
                    delay = (self.config.base_delay * (2 ** attempt)) + random.uniform(0.5, 2.0)
                    logger.warning("Microsoft 429 hit. Pausing this specific worker for %ss", delay)
                    await asyncio.sleep(delay)
                    continue

                response.raise_for_status()
                job_data = response.json().get("data", {})
                
                if job_data:
                    dept = job_data.get("department", "N/A")
                    work_site = ", ".join(job_data.get("efcustomTextWorkSite", []))
                    raw_body = job_data.get("jobDescription", "")
                    
                    job.description += f"Department: {dept}\nWorkplace Type: {work_site}\n\n### Job Profile\n"
                    job.description += BeautifulSoup(raw_body, "html.parser").get_text(separator="\n")
                break

            except Exception as exc:
                logger.warning("Network issue pulling details for MS ID %s: %s", job_id, exc)
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.base_delay * (attempt + 1))
        
        if close_client:
            await client.aclose()
            
        return job