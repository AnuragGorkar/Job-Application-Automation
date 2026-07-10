import asyncio
import json
import logging
import random
from typing import Optional

import httpx
from pydantic import ValidationError

from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.ats_scrapers.base_ats_scraper import BaseATSScraper
from app.utils.html_utils import clean_html

logger = logging.getLogger(__name__)

class WorkdayScraper(BaseATSScraper):
    # Local constant for your config file
    CONFIG_FILE = "workday_companies_config.json"

    def __init__(self):
        # Initialize parent with empty shells
        super().__init__(base_url="", params={})
        
        # Load the 1,000 company configuration map into memory once
        try:
            with open(self.CONFIG_FILE, "r") as f:
                self.workday_configs = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load Workday config: {e}")
            self.workday_configs = {}

    def map_to_ats_scraped_job(self, job: dict, company_name: str, config: dict) -> Optional[ScrapedJob]:
        title = job.get('title')
        external_path = job.get('externalPath', '')
        
        # Build the exact job URL using the pre-verified JSON data
        tenant = config.get('tenant', company_name)
        server = config.get('server', 'wd1')
        portal_id = config.get('portal_id', 'External')
        url = f"https://{tenant}.{server}.myworkdayjobs.com/en-US/{portal_id}{external_path}" if external_path else ""
        
        location = job.get('locationsText', 'Remote / Unspecified')
        clean_description = clean_html(job.get('jobDescription', ''))
        posted_at = job.get('postedOn', None)

        return ScrapedJob(
            title=title,
            location=location,
            description=clean_description,
            posted_at=posted_at,
            url=url,
            company=company_name,
            platform="Workday"
        )

    async def _scrape_single_company(self, company_name: str, config: dict, client: httpx.AsyncClient, semaphore: asyncio.Semaphore) -> list[ScrapedJob]:
        """Worker function for a single Workday company."""
        jobs = []
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
                                    scraped_job = self.map_to_ats_scraped_job(job, company_name, config)
                                    if scraped_job:
                                        jobs.append(scraped_job)
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

        return jobs

    async def fetch(self, dummy_company: str, client: httpx.AsyncClient) -> list[ScrapedJob]:
        """
        THE ORCHESTRATOR.
        This ignores the 'dummy_company' ("workday") passed by JobScraper, 
        and instead spins up tasks for all companies in the JSON.
        """
        if not self.workday_configs:
            logger.error("No Workday configurations loaded. Aborting.")
            return []

        logger.info(f"Starting Workday Orchestrator for {len(self.workday_configs)} companies...")

        # 15 concurrent companies is the sweet spot for speed vs. stability
        semaphore = asyncio.Semaphore(15)

        # Create the sub-tasks for all 1,000 companies
        tasks = [
            self._scrape_single_company(company_name, config, client, semaphore)
            for company_name, config in self.workday_configs.items()
        ]

        # Execute them all concurrently using the inherited client
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten the massive list of lists into a single list of ScrapedJobs
        all_workday_jobs = []
        for res in results:
            if isinstance(res, list):
                all_workday_jobs.extend(res)
            else:
                logger.error(f"A Workday company task crashed completely: {res}")

        logger.info(f"Workday Orchestrator finished. Passing {len(all_workday_jobs)} jobs back to JobScraper.")
        
        # Returns directly into the `job_batch = await self.job_queue.get()` of your JobScraper
        return all_workday_jobs