import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
import random
import re
import time
from asyncio import Queue
from typing import Optional

import httpx
from aiolimiter import AsyncLimiter
from pydantic import ValidationError

from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.ats_scrapers.base_ats_scraper import BaseATSScraper
from app.services.job_scrapers.scraper_config import ScraperConfig
from app.utils.html_utils import clean_html

logger = logging.getLogger(__name__)

class WorkdayScraper(BaseATSScraper):
    # Local constant for your config file
    CONFIG_FILE_PATH = "app/assets/workday_companies/final_workday_companies_config.json"

    def __init__(self, validation_queue: Queue, enrichment_queue: Queue, config: ScraperConfig | None = None):
        # Initialize parent with empty shells
        super().__init__(
            base_url="", 
            params={}, 
            validation_queue=validation_queue, 
            enrichment_queue=enrichment_queue, 
            config=config
        )
        
        # Load the 1,000 company configuration map into memory once
        try:
            with open(self.CONFIG_FILE_PATH, "r") as f:
                self.workday_configs = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load Workday config: {e}")
            self.workday_configs = {}
            
        # Initialize the Token Bucket Limiter (e.g., 5 requests per second)
        # This protects against Workday's aggressive Akamai WAF blocking your IP
        self.rate_limiter = AsyncLimiter(max_rate=5, time_period=1)
    
    def _parse_workday_date(self, posted_on: str) -> str:
        """Translates Workday's fixed relative time strings into valid ISO datetimes."""
        now = datetime.now(timezone.utc)
        
        if not posted_on:
            return now.isoformat()
            
        text = posted_on.lower()
        
        # The fixed Workday English format
        if "today" in text:
            return now.isoformat()
        if "yesterday" in text:
            return (now - timedelta(days=1)).isoformat()
            
        # Matches "Posted N Days Ago" and "Posted 30+ Days Ago"
        match = re.search(r'(\d+)', text)
        if match:
            days_ago = int(match.group(1))
            return (now - timedelta(days=days_ago)).isoformat()
            
        # Fallback if something completely unexpected arrives
        logger.warning(f"Unrecognized Workday date format: {posted_on}")
        return now.isoformat()

    def map_to_scraped_job(self, job: dict, company_name: str, config: dict) -> Optional[ScrapedJob]:
        title = job.get('title')
        external_path = job.get('externalPath', '')
        
        # Build the exact job URL using the pre-verified JSON data
        tenant = config.get('tenant', company_name)
        server = config.get('server', 'wd1')
        portal_id = config.get('portal_id', 'External')
        url = f"https://{tenant}.{server}.myworkdayjobs.com/en-US/{portal_id}{external_path}" if external_path else ""
        
        location = job.get('locationsText', 'Remote / Unspecified')
        
        # In Phase 1, description is left as a stub or empty string
        clean_description = clean_html(job.get('jobDescription', ''))
        posted_at = self._parse_workday_date(job.get('postedOn', None))

        return ScrapedJob(
            title=title,
            location=location,
            description=clean_description,
            posted_at=posted_at,
            url=url,
            company=company_name,
            platform="workday"
        )

    async def _scrape_single_company(self, company_name: str, config: dict, client: httpx.AsyncClient, semaphore: asyncio.Semaphore) -> None:
        """Worker function for a single Workday company."""
        offset = 0
        limit = 20
        total_jobs = 1

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        api_url = config["api_url"]

        # 1. SEMAPHORE APPLIED HERE: Restricts concurrent companies
        async with semaphore:
            while offset < total_jobs:
                payload = {"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""}
                page_success = False

                # 2. RETRY APPLIED HERE: Restricts failures to the specific pagination offset
                for attempt in range(3):
                    try:
                        r = await client.post(api_url, json=payload, headers=headers, timeout=15.0)
                        
                        if r.status_code == 200:
                            data = r.json()
                            raw_jobs = data.get("jobPostings", [])
                            total_jobs = data.get("total", 0) 
                            
                            if not raw_jobs:
                                page_success = True
                                break 
                                
                            for job in raw_jobs:
                                try:
                                    scraped_job = self.map_to_scraped_job(job, company_name, config)
                                    if scraped_job is not None:
                                        await self.validation_queue.put(scraped_job)
                                except ValidationError as validation_err:
                                    logger.debug(f"Validation error for {company_name}: {validation_err}")
                            
                            page_success = True
                            break # Success, exit the retry loop
                                
                        elif r.status_code in [429, 502, 503, 504]:
                            # Exponential backoff + jitter for WAF rate limits
                            delay = (2.0 * (2 ** attempt)) * random.uniform(0.8, 1.2)
                            logger.warning(f"Workday {r.status_code} for {company_name}. Retrying in {delay:.2f}s...")
                            await asyncio.sleep(delay)
                        else:
                            logger.error(f"Permanent Workday failure {r.status_code} for {company_name}.")
                            break # Unrecoverable error, exit retry loop

                    except Exception as e:
                        delay = (2.0 * (2 ** attempt)) * random.uniform(0.8, 1.2)
                        logger.warning(f"Network error for {company_name} at offset {offset}: {e}. Retrying...")
                        await asyncio.sleep(delay)

                if not page_success:
                    logger.error(f"Failed to fetch {company_name} at offset {offset} after 3 attempts. Halting.")
                    break # Stop paginating this company entirely

                offset += limit 
                await asyncio.sleep(0.5) # Polite pause between successful pages

    async def fetch(self, dummy_company: str, client: httpx.AsyncClient) -> int:
        """
        THE ORCHESTRATOR.
        This ignores the 'dummy_company' ("workday") passed by JobScraper, 
        and instead spins up tasks for all companies in the JSON.
        """
        if not self.workday_configs:
            logger.error("No Workday configurations loaded. Aborting.")
            return 0

        scrape_start_time = time.time()
        logger.info(f"Starting Workday Orchestrator for {len(self.workday_configs)} companies...")

        # Use the shared scraper config for concurrency while allowing overrides locally if needed.
        semaphore = asyncio.Semaphore(self.config.semaphore_value)

        # Create the sub-tasks for all 1,000 companies
        tasks = [
            self._scrape_single_company(company_name, config, client, semaphore)
            for company_name, config in self.workday_configs.items()
        ]

        # Execute them all concurrently using the inherited client
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # In this architecture, queued_count tracking relies on passing items into validation_queue
        # Returning len of tasks just as a placeholder since queues handle the flow dynamically.
        queued_count = len(tasks) 

        for res in results:
            if isinstance(res, Exception):
                logger.error(f"A Workday company task crashed completely: {res}")

        scrape_end_time = time.time()
        time_take = scrape_end_time-scrape_start_time
        logger.info("Workday Orchestrator finished. Jobs were pushed to the validation queue.")
        logger.info(f"Time taken to scrape workday jobs: {time_take//60} minutes {time_take%60} seconds.")
        return queued_count
    
    async def enrich(self, company_name: str, job: ScrapedJob, client: Optional[httpx.AsyncClient] = None) -> ScrapedJob:
        """Phase 2: Hits the hidden CXS API to extract the full HTML job description."""
        
        # 1. Look up the specific tenant from your loaded config map
        config = self.workday_configs.get(company_name, {})
        tenant = config.get('tenant', company_name)
        
        # 2. Convert the public HTML URL into the backend API URL
        api_detail_url = job.url.replace("/en-US/", f"/wday/cxs/{tenant}/")
        
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en-US",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        close_client = False
        if not client:
            client = httpx.AsyncClient()
            close_client = True
            
        try:
            # Wrap the request in the Token Bucket limiter to prevent 429 WAF blocks
            async with self.rate_limiter:
                resp = await client.get(api_detail_url, headers=headers, timeout=10.0)
            
            if resp.status_code == 200:
                data = resp.json()
                raw_html = data.get("jobPostingInfo", {}).get("jobDescription", "")
                
                if raw_html:
                    cleaned_desc = clean_html(raw_html)
                    # Append the detailed description to the summary description
                    job.description = f"{job.description}\n\n### Description\n{cleaned_desc}".strip()
            
            elif resp.status_code in [403, 429]:
                logger.warning(f"Rate limited or WAF blocked fetching details for {api_detail_url}")
                job.description += "\n\n### Description\n[Description fetch failed due to rate limit]"
                
        except Exception as e:
            logger.error(f"Failed to fetch description for {api_detail_url}: {e}")
            job.description += "\n\n### Description\n[Description fetch failed]"
            
        finally:
            if close_client:
                await client.aclose()
                
        return job