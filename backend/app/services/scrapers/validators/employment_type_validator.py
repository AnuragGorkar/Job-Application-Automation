import logging
import re
from typing import Optional

from app.schemas.scraped_job import ScrapedJob
from app.services.scrapers.validators.scraped_job_validator import ScrapedJobValidator

logger = logging.getLogger(__name__)

EMP_TYPE_EXCLUSION_PATTERNS = [
            r"\bintern\b", r"\binternship\b", r"\bco-op\b", 
            r"\bcontract\b", r"\bcontractor\b", r"\bpart-time\b",
            r"\bstudent\b"
        ]
EMP_TYPE_EXCLUSION_REGEX = re.compile("|".join(EMP_TYPE_EXCLUSION_PATTERNS), re.IGNORECASE)


class EmploymentTypeValidator(ScrapedJobValidator):
    def __init__(self, next_validator: Optional[ScrapedJobValidator] = None):
        super().__init__(next_validator)

    def validate(self, job: ScrapedJob) -> bool:
        try:
            if not job.title:
                return False
                
            if EMP_TYPE_EXCLUSION_REGEX.search(job.title):
                return False
                
        except Exception as exc:
            logger.exception("Error processing title: %s", exc)
            return False

        return self.check_next(job)