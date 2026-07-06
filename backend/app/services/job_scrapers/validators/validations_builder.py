import logging
from functools import reduce

from app.services.job_scrapers.validators.employment_type_validator import EmploymentTypeValidator
from app.services.job_scrapers.validators.location_validator import LocationValidator
from app.services.job_scrapers.validators.position_title_validator import PositionTitleValidator
from app.services.job_scrapers.validators.scraped_job_validator import ScrapedJobValidator
from app.services.job_scrapers.validators.time_window_validator import TimeWindowValidator
from app.services.job_scrapers.validators.url_validator import URLValidator

logger = logging.getLogger(__name__)


class ValidationsBuilder:
    # Use a single underscore for internal/protected class constants
    _validators_list = [
        LocationValidator,
        EmploymentTypeValidator,
        PositionTitleValidator,
        TimeWindowValidator,
        URLValidator
    ]

    # Change to classmethod so the function can cleanly access `cls._validators_list`
    @classmethod
    def get_all_validations(cls) -> ScrapedJobValidator:
        logger.debug("Building validation chain with %s validators", len(cls._validators_list))
        return reduce(
            lambda acc_instance, current_class: current_class(acc_instance),
            reversed(cls._validators_list),
            None
        )