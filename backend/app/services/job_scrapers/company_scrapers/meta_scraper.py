import asyncio
import json
import logging
import random
import re
from datetime import datetime
from queue import Queue
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.base_scraper import BaseScraper
from app.services.job_scrapers.scraper_config import ScraperConfig

logger = logging.getLogger(__name__)

META_JOBS_URL = (
    "https://www.metacareers.com/jobsearch/?sort_by_new=true"
    "&teams[0]=Software%20Engineering"
    "&teams[1]=University%20Grad%20-%20Engineering%2C%20Tech%20%26%20Design"
    "&teams[2]=Artificial%20Intelligence"
    "&offices[0]=Seattle%2C%20WA&offices[1]=San%20Francisco%2C%20CA"
    "&offices[2]=New%20York%2C%20NY&offices[3]=Austin%2C%20TX"
    "&offices[4]=Washington%2C%20DC&offices[5]=Bellevue%2C%20WA"
    "&offices[6]=Sunnyvale%2C%20CA&offices[7]=Boston%2C%20MA"
    "&offices[8]=Atlanta%2C%20GA&offices[9]=Menlo%20Park%2C%20CA"
    "&roles[0]=Full%20time%20employment"
)


class MetaScraper(BaseScraper):
    def __init__(self, job_queue: Queue, max_pages: int = 5, max_concurrency: int = 10, config: ScraperConfig | None = None):
        super().__init__(job_queue, config=config)
        self.company_name = "Meta"
        self.max_pages = max_pages
        self.max_concurrency = max_concurrency
        
        # Headers required to spoof browser behavior and bypass Meta's 400 Bad Request blocker
        self.fetch_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1"
        }

    async def _fetch_deep_description(self, client: httpx.AsyncClient, job_id: str) -> str:
        """Hits the canonical SEO endpoint to extract the full job description."""
        url = f"https://www.metacareers.com/jobs/{job_id}/"
        
        try:
            response = await client.get(url, headers=self.fetch_headers, timeout=15.0, follow_redirects=True)
            response.raise_for_status()
            html = response.text
            
            soup = BeautifulSoup(html, "html.parser")
            
            # Method 1: Look for JSON-LD schema (cleanest extraction)
            ld_json_scripts = soup.find_all("script", type="application/ld+json")
            for script in ld_json_scripts:
                if not script.string:
                    continue
                try:
                    data = json.loads(script.string)
                    if data.get("@type") == "JobPosting" and "description" in data:
                        return BeautifulSoup(data["description"], "html.parser").get_text(separator="\n").strip()
                except json.JSONDecodeError:
                    continue

            # Method 2: Regex extraction from pre-hydrated state
            match = re.search(r'"job_description":"(.*?)"', html)
            if match:
                raw_desc = match.group(1).encode('utf-8').decode('unicode_escape')
                return BeautifulSoup(raw_desc, "html.parser").get_text(separator="\n").strip()

            return "Description could not be parsed from HTML."

        except Exception as e:
            logger.warning("Failed to deep fetch description for Meta job %s: %s", job_id, e)
            return "Description fetch failed."

    def map_to_scraped_job(self, job: dict, company_name: str, deep_description: str) -> Optional[ScrapedJob]:
        """Maps the combined GraphQL and HTTPx data to the ScrapedJob schema."""
        job_id = str(job.get("id", ""))
        title = job.get("title", "").strip()

        locations = job.get("locations", [])
        if not isinstance(locations, list):
            locations = [locations] if locations else []
        location = ", ".join(locations) if locations else "USA"

        teams = ", ".join(job.get("teams", []))
        sub_teams = ", ".join(job.get("sub_teams", []))
        locations_str = " | ".join(locations)

        custom_desc = f"Company: {company_name}\n"
        custom_desc += f"Locations: {locations_str}\n"
        custom_desc += f"Team classification: {teams} ({sub_teams})\n\n"
        
        # Append the successfully scraped deep description, or fallback to the stub
        if deep_description and deep_description not in ["Description fetch failed.", "Description could not be parsed from HTML."]:
            custom_desc += f"### Description\n{deep_description}"
        else:
            custom_desc += f"### Role Summary\nAn opening for a {title} position within the {teams} department."

        posted_at = datetime.now()
        url = f"https://www.metacareers.com/jobs/{job_id}/"

        return ScrapedJob(
            title=title,
            location=location,
            description=custom_desc.strip(),
            posted_at=posted_at,
            url=url,
            company=company_name,
            platform=self.company_name,
        )

    async def fetch(self, company_name: str, client: httpx.AsyncClient) -> int:
        queued_count = 0
        graphql_payloads: list[list] = []

        # =========================================================================
        # PHASE 1: Gather raw Job IDs and metadata via Playwright & GraphQL
        # =========================================================================
        logger.info("Executing Phase 1: Gathering Job IDs via Playwright...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()

            async def handle_response(response):
                if "metacareers.com/graphql" in response.url and response.status == 200:
                    try:
                        res_json = await response.json()
                        data_block = res_json.get("data", {}).get("job_search_with_featured_jobs_v2", {})
                        if "all_jobs" in data_block:
                            graphql_payloads.append(data_block["all_jobs"])
                    except Exception as err:
                        logger.debug("Failed to decode intercepted GraphQL payload: %s", err)

            page.on("response", handle_response)

            try:
                await page.goto(META_JOBS_URL, wait_until="networkidle", timeout=30000)

                for page_num in range(1, self.max_pages):
                    see_more_btn = page.locator('button:has-text("See More")')
                    if await see_more_btn.count() > 0 and await see_more_btn.is_visible():
                        logger.info("Clicking pagination 'See More' on page %s", page_num)
                        await see_more_btn.click()
                        await page.wait_for_timeout(2500)
                    else:
                        break
            except Exception as exc:
                logger.error("Error paginating through Meta Careers: %s", exc)
            finally:
                await context.close()
                await browser.close()

        # Deduplicate the raw GraphQL jobs
        unique_raw_jobs = {}
        for jobs_list in graphql_payloads:
            for raw_job in jobs_list:
                job_id = raw_job.get("id")
                if job_id and job_id not in unique_raw_jobs:
                    unique_raw_jobs[job_id] = raw_job

        logger.info("Phase 1 Complete. Found %s unique raw Meta jobs.", len(unique_raw_jobs))
        if not unique_raw_jobs:
            return 0

        # =========================================================================
        # PHASE 2: Fetch deep descriptions concurrently and map to final schema
        # =========================================================================
        logger.info("Executing Phase 2: Fetching deep HTML descriptions concurrently...")
        semaphore = asyncio.Semaphore(self.max_concurrency or self.config.semaphore_value)

        async def process_job_with_description(raw_job: dict) -> Optional[ScrapedJob]:
            job_id = raw_job.get("id")
            async with semaphore:
                # Slight sleep prevents hammering Meta's edge servers all at exactly 0.001s
                await asyncio.sleep(random.uniform(0.1, 0.6))
                deep_desc = await self._fetch_deep_description(client, job_id)
                
                try:
                    return self.map_to_scraped_job(raw_job, company_name, deep_desc)
                except Exception as map_err:
                    logger.exception("Failed mapping Meta raw job ID %s: %s", job_id, map_err)
                    return None

        detail_tasks = [process_job_with_description(job) for job in unique_raw_jobs.values()]
        detail_results = await asyncio.gather(*detail_tasks)

        for job in detail_results:
            if job is not None:
                await self.job_queue.put(job)
                queued_count += 1
        
        logger.info("Successfully fully extracted %s Meta listings. Passing to validators...", len(detail_results))
        return queued_count