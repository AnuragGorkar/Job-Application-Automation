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
from aiolimiter import AsyncLimiter

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
    def __init__(self, validation_queue: Queue, enrichment_queue: Queue, max_pages: int = 5, max_concurrency: int = 10, config: ScraperConfig | None = None):
        super().__init__(
            validation_queue=validation_queue,
            enrichment_queue=enrichment_queue, 
            config=config
        )
        self.company_name = "Meta"
        self.max_pages = max_pages
        self.max_concurrency = max_concurrency
        
        self.fetch_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1"
        }

        self.rate_limiter = AsyncLimiter(max_rate=5, time_period=1)

    def map_to_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:
        """Maps the raw GraphQL payload into a summary ScrapedJob object for validation."""
        job_id = str(job.get("id", ""))
        title = job.get("title", "").strip()

        locations = job.get("locations", [])
        if not isinstance(locations, list):
            locations = [locations] if locations else []
        location = ", ".join(locations) if locations else "USA"

        teams = ", ".join(job.get("teams", []))
        sub_teams = ", ".join(job.get("sub_teams", []))
        
        # We start with a summary description. Enrichment will append to this later.
        custom_desc = f"Company: {company_name}\nLocations: {' | '.join(locations)}\nTeam: {teams} ({sub_teams})\n"

        return ScrapedJob(
            title=title,
            location=location,
            description=custom_desc.strip(),
            posted_at=datetime.now(),
            url=f"https://www.metacareers.com/jobs/{job_id}/",
            company=company_name,
            platform=self.company_name,
        )

    async def fetch(self, company_name: str, client: httpx.AsyncClient) -> int:
        queued_count = 0
        graphql_payloads: list[list] = []

        logger.info("Executing Phase 1: Gathering Meta Job IDs via Playwright...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            page = await context.new_page()

            async def handle_response(response):
                if "metacareers.com/graphql" in response.url and response.status == 200:
                    try:
                        res_json = await response.json()
                        data_block = res_json.get("data", {}).get("job_search_with_featured_jobs_v2", {})
                        if "all_jobs" in data_block:
                            graphql_payloads.append(data_block["all_jobs"])
                    except Exception as err:
                        logger.debug("Failed to decode Meta GraphQL payload: %s", err)

            page.on("response", handle_response)

            try:
                await page.goto(META_JOBS_URL, wait_until="networkidle", timeout=30000)
                for page_num in range(1, self.max_pages):
                    see_more_btn = page.locator('button:has-text("See More")')
                    if await see_more_btn.count() > 0 and await see_more_btn.is_visible():
                        await see_more_btn.click()
                        await page.wait_for_timeout(2500)
                    else:
                        break
            except Exception as exc:
                logger.error("Error paginating through Meta Careers: %s", exc)
            finally:
                await context.close()
                await browser.close()

        unique_raw_jobs = {raw_job.get("id"): raw_job for jobs_list in graphql_payloads for raw_job in jobs_list if raw_job.get("id")}
        
        # Map them to summary jobs and immediately push them to the validation queue
        for raw_job in unique_raw_jobs.values():
            summary_job = self.map_to_scraped_job(raw_job, company_name)
            if summary_job:
                await self.validation_queue.put(summary_job)
                queued_count += 1
                
        logger.info("Phase 1 Complete. Pushed %s summary Meta jobs to validation queue.", queued_count)
        return queued_count

    async def enrich(self, company_name: str, job: ScrapedJob, client: Optional[httpx.AsyncClient] = None) -> ScrapedJob:
        """Phase 2: Hits the Canonical SEO endpoint to extract the full job description."""
        job_id = job.url.rstrip('/').split('/')[-1]
        
        close_client = False
        if not client:
            client = httpx.AsyncClient()
            close_client = True
            
        try:
            # Replaced the random jitter with the strict token bucket rate limiter
            async with self.rate_limiter:
                response = await client.get(job.url, headers=self.fetch_headers, timeout=15.0, follow_redirects=True)
                
            response.raise_for_status()
            
            html = response.text
            soup = BeautifulSoup(html, "html.parser")
            deep_desc = "Description could not be parsed."
            
            # Method 1: Look for JSON-LD schema (cleanest extraction)
            ld_json_scripts = soup.find_all("script", type="application/ld+json")
            for script in ld_json_scripts:
                if script.string:
                    try:
                        data = json.loads(script.string)
                        if data.get("@type") == "JobPosting" and "description" in data:
                            deep_desc = BeautifulSoup(data["description"], "html.parser").get_text(separator="\n").strip()
                            break
                    except json.JSONDecodeError:
                        continue

            if deep_desc == "Description could not be parsed.":
                # Method 2: Regex extraction
                match = re.search(r'"job_description":"(.*?)"', html)
                if match:
                    raw_desc = match.group(1).encode('utf-8').decode('unicode_escape')
                    deep_desc = BeautifulSoup(raw_desc, "html.parser").get_text(separator="\n").strip()
            
            job.description += f"\n\n### Description\n{deep_desc}"
            
        except Exception as e:
            logger.warning("Failed to deep fetch description for Meta job %s: %s", job_id, e)
            job.description += "\n\n### Description\n[Description fetch failed]"
        finally:
            if close_client:
                await client.aclose()
                
        return job