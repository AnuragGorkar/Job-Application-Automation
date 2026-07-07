import asyncio
import logging
import random
from datetime import datetime
from typing import Optional
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class MicrosoftScraper(BaseScraper):
    def __init__(self, max_concurrency: int = 5):
        self.company_name = "Microsoft"
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

    def map_to_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:
        title = job.get("name", "").strip()
        job_id = str(job.get("id", ""))

        emp_type_arr = job.get("efcustomTextEmploymentType", [])
        schedule_type = emp_type_arr[0] if emp_type_arr else "Full-Time"
        
        dept = job.get("department", "N/A")
        loc_list = " | ".join(job.get("locations", []))
        work_site = ", ".join(job.get("efcustomTextWorkSite", []))

        custom_desc = f"Company: {company_name}\n"
        custom_desc += f"Locations: {loc_list}\n"
        custom_desc += f"Department: {dept}\n"
        custom_desc += f"Workplace Type: {work_site}\n\n"

        raw_body = job.get("jobDescription", "")
        custom_desc += "### Job Profile\n" + BeautifulSoup(raw_body, "html.parser").get_text(separator="\n")

        raw_ts = job.get("postedTs")
        try:
            posted_at = datetime.utcfromtimestamp(float(raw_ts)) if raw_ts else datetime.now()
        except (ValueError, TypeError):
            posted_at = datetime.now()

        url = job.get("publicUrl", f"https://apply.careers.microsoft.com/careers/job/{job_id}")
        locations_arr = job.get("locations", [])
        location = locations_arr[0] if locations_arr else "USA"

        return ScrapedJob(
            title=title,
            location=location,
            description=custom_desc.strip(),
            posted_at=posted_at,
            url=url,
            company=company_name,
            platform=self.company_name,
        )

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

    async def _fetch_search_batch(self, base_params: dict, offset: int, client: httpx.AsyncClient) -> tuple[list[str], int]:
        """Fetches a single search batch and returns Job IDs and the total hit count."""
        params = dict(base_params)
        params["start"] = [str(offset)]

        try:
            response = await client.get(self.search_api_url, params=params, timeout=10.0, headers=self.headers)
            response.raise_for_status()
            data = response.json().get("data", {})

            positions = data.get("positions", [])
            total_hits = data.get("count", 0)
            
            # Map raw IDs. All validation/filtering happens downstream in the validator chain.
            job_ids = [str(pos.get("id")) for pos in positions if pos.get("id")]
            return job_ids, total_hits
        except Exception as exc:
            logger.error("Failed executing search batch at offset %s: %s", offset, exc)
            return [], 0

    async def _gather_ids_for_url(self, url: str, client: httpx.AsyncClient, semaphore: asyncio.Semaphore) -> set[str]:
        """Applies the Amazon parallel pagination pattern to a single Microsoft search URL."""
        base_params = self._parse_url_to_api_params(url)
        collected_ids = set()

        # Extract total hits right from the first call
        first_batch_ids, total_hits = await self._fetch_search_batch(base_params, 0, client)
        collected_ids.update(first_batch_ids)

        if total_hits == 0 or not first_batch_ids:
            return collected_ids

        # Microsoft APIs typically return 20 jobs per page. Fallback to 20 if dynamic check fails.
        page_size = len(first_batch_ids) or 20
        offsets = [offset for offset in range(page_size, total_hits, page_size)]

        async def bounded_search_fetch(offset: int) -> list[str]:
            async with semaphore:
                batch_ids, _ = await self._fetch_search_batch(base_params, offset, client)
                return batch_ids

        if offsets:
            batch_results = await asyncio.gather(*(bounded_search_fetch(offset) for offset in offsets))
            for batch in batch_results:
                collected_ids.update(batch)

        return collected_ids

    async def _fetch_single_job_detail(self, client: httpx.AsyncClient, job_id: str, company_name: str) -> Optional[ScrapedJob]:
        """Retrieves and processes deep profile descriptions for an individual target ID."""
        detail_params = {"position_id": job_id, "domain": "microsoft.com", "hl": "en"}
        max_retries = 3
        base_delay = 3.0

        for attempt in range(max_retries):
            try:
                response = await client.get(self.details_api_url, params=detail_params, timeout=12.0, headers=self.headers)
                
                # Dynamic Rate Limit (429) Handling - Microsoft is aggressive here
                if response.status_code == 429:
                    delay = (base_delay * (2 ** attempt)) + random.uniform(0.5, 2.0)
                    logger.warning("Rate limited (429) on job %s. Backing off for %ss...", job_id, round(delay, 2))
                    await asyncio.sleep(delay)
                    continue

                response.raise_for_status()
                job_data = response.json().get("data", {})
                if not job_data:
                    return None

                return self.map_to_scraped_job(job_data, company_name)

            except httpx.RequestError as req_err:
                logger.warning("Network issue pulling details for ID %s (Attempt %s): %s", job_id, attempt + 1, req_err)
                if attempt < max_retries - 1:
                    await asyncio.sleep(base_delay * (attempt + 1))
            except Exception as exc:
                logger.exception("Fatal processing fault on Microsoft profile ID %s: %s", job_id, exc)
                break

        return None

    async def fetch(self, company_name: str, client: httpx.AsyncClient) -> list[ScrapedJob]:
        unique_job_ids: set[str] = set()
        semaphore = asyncio.Semaphore(self.max_concurrency)

        # Phase 1: Parallelize the collection of targeted Job IDs across all URLs using the Amazon pattern
        logger.info("Executing Phase 1: Gathering Job IDs concurrently...")
        
        search_tasks = [self._gather_ids_for_url(url, client, semaphore) for url in self.frontend_urls]
        search_results = await asyncio.gather(*search_tasks)

        for id_set in search_results:
            unique_job_ids.update(id_set)

        logger.info("Phase 1 Complete. Found %s total raw jobs. Passing to Phase 2.", len(unique_job_ids))
        if not unique_job_ids:
            return []

        # Phase 2: Parallelize deep-profile fetches for descriptions (Required for MS API)
        logger.info("Executing Phase 2: Fetching full descriptions concurrently...")

        async def bounded_detail_fetch(j_id: str) -> Optional[ScrapedJob]:
            async with semaphore:
                # Slight sleep protects worker nodes from rapid 429 penalties during detail fetching
                await asyncio.sleep(random.uniform(0.2, 0.8))
                return await self._fetch_single_job_detail(client, j_id, company_name)

        detail_tasks = [bounded_detail_fetch(job_id) for job_id in unique_job_ids]
        detail_results = await asyncio.gather(*detail_tasks)

        scraped_jobs = [job for job in detail_results if job is not None]
        logger.info("Successfully extracted %s raw Microsoft jobs. Passing to validator chain...", len(scraped_jobs))
        
        return scraped_jobs