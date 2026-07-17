import logging
from queue import Queue
from typing import Final, Optional

from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.ats_scrapers.base_ats_scraper import BaseATSScraper
from app.utils.html_utils import clean_html

class AshbyScraper(BaseATSScraper):
    BASE_URL: Final[str] = "https://api.ashbyhq.com/posting-api/job-board/"
    PARAMS: Final[dict] = {
        "includeCompensation" : "true"
        }

    def __init__(self, validation_queue: Queue, enrichment_queue: Queue):
        super().__init__(
            base_url=self.BASE_URL,
            params=self.PARAMS,
            validation_queue=validation_queue,
            enrichment_queue=enrichment_queue
        )
    
    def map_to_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:
        title = job.get('title')
        url = job.get('jobUrl')
        location = job.get('location')

        clean_description = clean_html(job.get('description', ''))

        posted_at = job.get('publishedAt', None)

        return ScrapedJob(
            title=title,
            location=location,
            description=clean_description,
            posted_at=posted_at,
            url=url,
            company=company_name,
            platform="ashby"
        )