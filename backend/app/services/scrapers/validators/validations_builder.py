from functools import reduce

from app.services.scrapers.validators.employment_type_validator import EmploymentTypeValidator
from app.services.scrapers.validators.location_validator import LocationValidator
from app.services.scrapers.validators.position_title_validator import PositionTitleValidator
from app.services.scrapers.validators.scraped_job_validator import ScrapedJobValidator
from app.services.scrapers.validators.time_window_validator import TimeWindowValidator
from app.services.scrapers.validators.url_validator import URLValidator

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
        return reduce(
            lambda acc_instance, current_class: current_class(acc_instance),
            reversed(cls._validators_list),
            None
        )