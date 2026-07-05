from app.schemas.scraped_job import ScrapedJob
from app.services.scrapers.validators.scraped_job_validator import ScrapedJobValidator


class URLValidator(ScrapedJobValidator):
    def _do_validate(self, job: ScrapedJob) -> bool:
        try:
            # Must exist and be a valid HTTP web link
            if not job.url or not job.url.startswith("http"):
                return False
                
            # Filter out internal ATS test links if any leak through
            if "test" in job.url.lower() or "demo" in job.url.lower():
                return False
                
        except Exception as e:
            print(f"[URLValidator] Error processing URL: {e}")
            return False

        return self.pass_to_next_validator(job)