import logging
from asyncio import Queue
from typing import Final, Optional

from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.ats_scrapers.base_ats_scraper import BaseATSScraper
from app.utils.html_utils import clean_html

logger = logging.getLogger(__name__)

class SmartRecruitersScraper(BaseATSScraper):
    # SmartRecruiters API endpoint
    BASE_URL: Final[str] = "https://api.smartrecruiters.com/v1/companies/"
    
    # 3-5 is a safe concurrent request limit to avoid WAF blocks
    SR_SEMAPHORE = 4 

    def __init__(self, validation_queue: Queue, enrichment_queue: Queue):
        super().__init__(
            base_url=self.BASE_URL,
            params={}, # Usually pagination is handled via limit/offset in query strings
            validation_queue=validation_queue,
            enrichment_queue=enrichment_queue,
            base_ats_fetch_semaphore=self.SR_SEMAPHORE,
        )
    
    def build_company_url(self, company_name: str) -> str:
        # Standard SmartRecruiters endpoint for job postings
        return f"{self.base_url}{company_name}/postings"
    
    def map_to_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:
        # SmartRecruiters API response fields
        title = job.get('name')
        url = job.get('ref') # Often contains the job page URL
        
        location = job.get('location', {}).get('city')
        
        # SmartRecruiters often provides descriptions in a dedicated field
        raw_desc = job.get('jobAd', {}).get('sections', {})
        # Flattening sections if they exist as a list/dict
        clean_description = clean_html(str(raw_desc)) 
        
        posted_at = job.get('releasedDate', None)

        return ScrapedJob(
            title=title,
            description=clean_description,
            location=location,
            posted_at=posted_at,
            url=url,
            company=company_name,
            platform="smartrecruiters"
        )