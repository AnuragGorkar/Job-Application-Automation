import asyncio
import logging
from datetime import datetime
from typing import Optional
from playwright.async_api import async_playwright

import httpx

from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.base_scraper import BaseScraper

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
    def __init__(self, max_pages: int = 5):
        self.company_name = "Meta"
        self.max_pages = max_pages
        # Common US state abbreviations to look for in location data strings
        self.us_states = {"CA", "WA", "NY", "TX", "DC", "MA", "GA", "VA", "CO", "IL"}

    def map_to_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:
        """Implements the mandatory BaseScraper abstract method contract."""
        job_id = str(job.get("id", ""))
        title = job.get("title", "").strip()

        # 1. Geographic Filtering
        locations = job.get("locations", [])
        if not isinstance(locations, list):
            locations = [locations] if locations else []


        # Primary location selection
        location = ", ".join(locations) if locations else "USA"

        # 2. Construct Custom Unified Description String
        teams = ", ".join(job.get("teams", []))
        sub_teams = ", ".join(job.get("sub_teams", []))
        locations_str = " | ".join(locations)

        custom_desc = f"Company: {company_name}\n"
        custom_desc += f"Locations: {locations_str}\n"
        custom_desc += f"Team classification: {teams} ({sub_teams})\n\n"
        custom_desc += f"### Role Summary\nAn opening for a {title} position within the {teams} department."

        # 3. Handle Timestamps Safely
        # Meta's payload rarely has raw epoch timestamps. Fallback to current time.
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

    async def fetch(self, company_name: str, client: httpx.AsyncClient) -> list[ScrapedJob]:
        graphql_payloads: list[list] = []

        async with async_playwright() as p:
            # Launch browser with sandbox flags to run inside container environments smoothly
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()

            # Event handler to intercept response streams asynchronously
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
                logger.info("Opening Meta Careers network tracking context...")
                await page.goto(META_JOBS_URL, wait_until="networkidle", timeout=30000)

                # Pagination Handler loop
                for page_num in range(1, self.max_pages):
                    see_more_btn = page.locator('button:has-text("See More")')
                    
                    # Verify if button is present and click-ready
                    if await see_more_btn.count() > 0 and await see_more_btn.is_visible():
                        logger.info("Clicking pagination 'See More' on page %s", page_num)
                        await see_more_btn.click()
                        # Allow network stream a clean window to settle down and emit frames
                        await page.wait_for_timeout(2500)
                    else:
                        break

            except Exception as exc:
                logger.error("Error navigating or paginating through Meta Careers: %s", exc)
            finally:
                await context.close()
                await browser.close()

        # Map and parse the accumulated payloads safely outside the browser cycle
        seen_job_ids = set()
        for jobs_list in graphql_payloads:
            for raw_job in jobs_list:
                job_id = raw_job.get("id")
                if not job_id or job_id in seen_job_ids:
                    continue

                try:
                    job_obj = self.map_to_scraped_job(raw_job, company_name)
                    if job_obj:
                        scraped_jobs.append(job_obj)
                        seen_job_ids.add(job_id)
                except Exception as map_err:
                    logger.exception("Failed mapping Meta raw job ID %s: %s", job_id, map_err)

        logger.info("Successfully scraped %s unique Meta listings.", len(scraped_jobs))
        return scraped_jobs