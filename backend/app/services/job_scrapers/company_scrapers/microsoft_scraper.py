import asyncio
import logging
import random
from datetime import datetime, timedelta
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
        
        self.cutoff_date = datetime.now() - timedelta(days=1)

    def map_to_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:
        """Implements the mandatory BaseScraper abstract method contract."""
        title = job.get("name", "").strip()
        job_id = str(job.get("id", ""))

        # Extract standard structural fields
        emp_type_arr = job.get("efcustomTextEmploymentType", [])
        schedule_type = emp_type_arr[0] if emp_type_arr else "Full-Time"
        
        dept = job.get("department", "N/A")
        loc_list = " | ".join(job.get("locations", []))
        work_site = ", ".join(job.get("efcustomTextWorkSite", []))

        # Build custom presentation summary
        custom_desc = f"Company: {company_name}\n"
        custom_desc += f"Locations: {loc_list}\n"
        custom_desc += f"Department: {dept}\n"
        custom_desc += f"Workplace Type: {work_site}\n\n"

        raw_body = job.get("jobDescription", "")
        custom_desc += "### Job Profile\n" + BeautifulSoup(raw_body, "html.parser").get_text(separator="\n")

        # Parse date representation cleanly
        raw_ts = job.get("postedTs")
        try:
            posted_at = datetime.utcfromtimestamp(float(raw_ts)) if raw_ts else datetime.now()
        except (ValueError, TypeError):
            posted_at = datetime.now()

        url = job.get("publicUrl", f"https://apply.careers.microsoft.com/careers/job/{job_id}")

        # Primary location selection fallback
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
        """Translates a frontend search view URL into raw API request parameters."""
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

    async def _gather_ids_from_url(self, client: httpx.AsyncClient, frontend_url: str) -> set[str]:
        """Paginates a single search category URL sequentially and extracts candidate job IDs."""
        collected_ids = set()
        params = self._parse_url_to_api_params(frontend_url)
        
        start = int(params.get("start", ["0"])[0])
        total_count = None
        current_time_ts = datetime.now().timestamp()
        cutoff_seconds = 86400.0  # 24 Hours

        while total_count is None or start < total_count:
            params["start"] = [str(start)]
            try:
                response = await client.get(self.search_api_url, params=params, timeout=10.0, headers=self.headers)
                response.raise_for_status()
                data = response.json().get("data", {})

                positions = data.get("positions", [])
                if not positions:
                    break

                if total_count is None:
                    total_count = data.get("count", 0)

                for pos in positions:
                    # 1. Geography Filter
                    locations = pos.get("standardizedLocations", [])
                    if "US" not in locations and not any(loc.endswith(", US") for loc in locations):
                        continue

                    # 2. Strict 24-Hour Cutoff Filter
                    posted_ts = pos.get("postedTs")
                    if posted_ts:
                        age_seconds = current_time_ts - float(posted_ts)
                        if age_seconds <= cutoff_seconds:
                            collected_ids.add(str(pos.get("id")))

                start += len(positions)
                await asyncio.sleep(0.3)  # Gentle pagination delay

            except Exception as exc:
                logger.error("Failed executing search batch pagination at offset %s: %s", start, exc)
                break

        return collected_ids

    async def _fetch_single_job_detail(self, client: httpx.AsyncClient, job_id: str, company_name: str) -> Optional[ScrapedJob]:
        """Retrieves and processes deep profile descriptions for an individual target ID."""
        detail_params = {"position_id": job_id, "domain": "microsoft.com", "hl": "en"}
        max_retries = 3
        base_delay = 3.0

        for attempt in range(max_retries):
            try:
                response = await client.get(self.details_api_url, params=detail_params, timeout=12.0, headers=self.headers)
                
                # Dynamic Rate Limit (429) Handling
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
                logger.exception("Fatal processing parsing fault on Microsoft profile ID %s: %s", job_id, exc)
                break

        return None

    async def fetch(self, company_name: str, client: httpx.AsyncClient) -> list[ScrapedJob]:
        scraped_jobs: list[ScrapedJob] = []
        unique_job_ids: set[str] = set()

        # Phase 1: Parallelize the collection of targeted Job IDs across all entry URLs
        logger.info("Executing Phase 1: Gathering Job IDs concurrently across categories...")
        search_tasks = [self._gather_ids_from_url(client, url) for url in self.frontend_urls]
        search_results = await asyncio.gather(*search_tasks)

        for id_set in search_results:
            unique_job_ids.update(id_set)

        logger.info("Phase 1 Complete. Found %s unique, 24-hour US job matches.", len(unique_job_ids))
        if not unique_job_ids:
            return []

        # Phase 2: Parallelize deep-profile fetches with bounded concurrency management
        logger.info("Executing Phase 2: Fetching full descriptions concurrently...")
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def bounded_detail_fetch(client_instance: httpx.AsyncClient, j_id: str) -> Optional[ScrapedJob]:
            async with semaphore:
                # Standard polite processing spacing to help protect worker nodes from 429 penalties
                await asyncio.sleep(random.uniform(0.2, 0.8))
                return await self._fetch_single_job_detail(client_instance, j_id, company_name)

        detail_tasks = [bounded_detail_fetch(client, job_id) for job_id in unique_job_ids]
        detail_results = await asyncio.gather(*detail_tasks)

        # Drop None elements resulting from fetch failures or validation exclusions
        scraped_jobs = [job for job in detail_results if job is not None]
        logger.info("Successfully extracted %s fully hydrated Microsoft jobs.", len(scraped_jobs))
        return scraped_jobs