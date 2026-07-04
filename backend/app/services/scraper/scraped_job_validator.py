from abc import abstractmethod, ABC
from typing import Optional
import timestamp_str
from datetime import datetime, timezone, timedelta

from app.core.patterns import INTL_REGEX, US_LOCATION_REGEX, SENIORITY_REGEX, ROLE_REGEX
from app.core.schemas.scraped_job import ScrapedJob

class ScrapedJobValidator(ABC):
    def __init__(self, next_validator: Optional[ScrapedJobValidator] = None):
        self.next_validator = next_validator

    @abstractmethod
    def validate(self, job: ScrapedJob) -> bool:
        pass

    def check_next(self, job: ScrapedJob) -> bool:
        if self.next_validator:
            return self.next_validator.validate(job)
        return True

class LocationValidator(ScrapedJobValidator):
    def validate(self, job: ScrapedJob) -> bool:
        try: 
            if not job.location:
                return False
            if INTL_REGEX.search(job.location):
                return False
            if not US_LOCATION_REGEX.search(job.location):
                return False
        except Exception as e:
            print(f"[LocationValidator] Error processing location string: {e}")
            return False

        return self.check_next(job)

class PositionTitleValidator(ScrapedJobValidator):
    def validate(self, job: ScrapedJob) -> bool:
        try:
            if not job.title:
                return False
            if SENIORITY_REGEX.search(job.title):
                return False
            if not ROLE_REGEX.search(job.title):
                return False
        except Exception as e:
            print(f"[PositionTitleValidator] Error processing position title: {e}")
            return False

        return self.check_next(job)

class TimeWindowValidator(ScrapedJobValidator):
    def validate(self, job: ScrapedJob) -> bool:    
        try:
            if not job.posted_time:
                return False
        
            job_time = job.posted_time
            if job_time.tzinfo is None:
                job_time = job_time.replace(tzinfo=timezone.utc)
            time_diff = datetime.now(timezone.utc) - job_time    

            if time_diff > timedelta(hours=24):
                return False
        except Exception as e:
            print(f"[TimeWindowValidator] Error processing timestamp object: {e}")
            return False
            
        return self.check_next(job)