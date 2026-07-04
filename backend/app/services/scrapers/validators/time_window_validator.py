from datetime import datetime, timedelta, timezone

from app.schemas.scraped_job import ScrapedJob
from app.services.scrapers.validators.scraped_job_validator import ScrapedJobValidator


class TimeWindowValidator(ScrapedJobValidator):
    def validate(self, job: ScrapedJob) -> bool:    
        try:
            if not job.posted_at:
                return False
        
            job_time = job.posted_at
            if job_time.tzinfo is None:
                job_time = job_time.replace(tzinfo=timezone.utc)
            time_diff = datetime.now(timezone.utc) - job_time    

            if time_diff > timedelta(hours=24*30):
                return False
        except Exception as e:
            print(f"[TimeWindowValidator] Error processing timestamp object: {e}")
            return False
            
        return self.check_next(job)