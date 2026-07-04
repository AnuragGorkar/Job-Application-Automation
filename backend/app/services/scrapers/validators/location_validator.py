import re

from app.schemas.scraped_job import ScrapedJob
from app.services.scrapers.validators.scraped_job_validator import ScrapedJobValidator


# ==========================================
# US-Only Location Targeting
# ==========================================
# Explicit country-level indicators
US_COUNTRY_PATTERNS = [r"\bunited states\b", r"\bu\.s\.a?\.?\b", r"\busa\b", r"\bus\b"]

# US state abbreviations + a handful of major tech-hub cities, all matched
# as whole words/tokens (so "ca" only matches ", CA" not "canada" or
# "scale"). State names spelled out are also included for boards that
# write full names.
US_STATE_ABBR = [
    "al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il","in",
    "ia","ks","ky","la","me","md","ma","mi","mn","ms","mo","mt","ne","nv",
    "nh","nj","nm","ny","nc","nd","oh","ok","or","pa","ri","sc","sd","tn",
    "tx","ut","vt","va","wa","wv","wi","wy","dc",
]
US_CITIES = [
    "san francisco", "new york", "seattle", "austin", "raleigh", "durham",
    "boston", "chicago", "los angeles", "san jose", "san diego", "denver",
    "atlanta", "miami", "dallas", "houston", "washington", "portland",
    "pittsburgh", "detroit", "minneapolis", "phoenix", "charlotte",
    "nashville", "salt lake city", "philadelphia", "columbus",
]
US_LOCATION_PATTERNS = (
    US_COUNTRY_PATTERNS
    + [rf"\b{abbr}\b" for abbr in US_STATE_ABBR]
    + [rf"\b{re.escape(city)}\b" for city in US_CITIES]
)
US_LOCATION_REGEX = re.compile("|".join(US_LOCATION_PATTERNS), re.IGNORECASE)

# Anything explicitly tagged as international gets excluded outright, even
# if it happens to also contain a US-looking token (rare, but cheap safety net)
INTL_PATTERNS = [
    r"\beurope\b", r"\buk\b", r"\bunited kingdom\b", r"\blondon\b",
    r"\bindia\b", r"\bgermany\b", r"\bemea\b", r"\bapac\b", r"\bcanada\b",
    r"\btoronto\b", r"\bireland\b", r"\bsingapore\b", r"\baustralia\b",
    r"\blatam\b", r"\bmexico\b", r"\bbrazil\b",
]
INTL_REGEX = re.compile("|".join(INTL_PATTERNS), re.IGNORECASE)


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