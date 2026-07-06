import functools
import logging
from abc import ABC, abstractmethod
from typing import Optional
from app.schemas.scraped_job import ScrapedJob
from collections import defaultdict

logger = logging.getLogger(__name__)

class ScrapedJobValidator(ABC):
    def __init__(self, next_validator: Optional['ScrapedJobValidator'] = None):
        self.next_validator = next_validator
        self.validation_counts = defaultdict(lambda: defaultdict(int))

    def validate(self, job: ScrapedJob) -> bool:
        """Template method: counts things safely, then runs the true validation."""
        self.validation_counts["all_platforms"]["total"] += 1
        self.validation_counts[job.platform]["total"] += 1
        
        # Run specific subclass validation logic
        is_valid = self._do_validate(job)
        
        if is_valid:
            self.validation_counts["all_platforms"]["pass"] += 1
            self.validation_counts[job.platform]["pass"] += 1
            # Pass down the chain of responsibility
            return self.pass_to_next_validator(job)
        else:
            self.validation_counts["all_platforms"]["fail"] += 1
            self.validation_counts[job.platform]["fail"] += 1
            return False

    @abstractmethod
    def _do_validate(self, job: ScrapedJob) -> bool:
        """Each validator subclass implements this clean rule logic."""
        pass

    def pass_to_next_validator(self, job: ScrapedJob) -> bool:
        if self.has_next():
            # Ensures correct forward reference
            return self.next_validator.validate(job)
        return True

    def has_next(self) -> bool: 
        return self.next_validator is not None

    def log_validation_stats(self):
        """Logs aggregated statistics for total execution and broken down per platform."""
        # 1. Build string for total baseline stats
        total_data = self.validation_counts.get("all_platforms", {})
        stats_summary = (
            f"[{self.__class__.__name__} Summary] "
            f"TOTAL -> Scraped: {total_data.get('total', 0)} | "
            f"Passed: {total_data.get('pass', 0)} | "
            f"Failed: {total_data.get('fail', 0)}"
        )
        logger.info(stats_summary)

        # 2. Iterate and log individual platform components
        for platform, counts in self.validation_counts.items():
            if platform == "all_platforms":
                continue
            platform_summary = (
                f"  -> Platform [{platform}] :: "
                f"Scraped: {counts.get('total', 0)} | "
                f"Passed: {counts.get('pass', 0)} | "
                f"Failed: {counts.get('fail', 0)}"
            )
            logger.info(platform_summary)

        # 3. Recursively bubble down the remaining Chain of Responsibility nodes
        if self.has_next():
            self.next_validator.log_validation_stats()