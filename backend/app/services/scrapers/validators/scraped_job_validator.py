import logging
from abc import ABC, abstractmethod
from typing import Optional

from app.schemas.scraped_job import ScrapedJob

logger = logging.getLogger(__name__)


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