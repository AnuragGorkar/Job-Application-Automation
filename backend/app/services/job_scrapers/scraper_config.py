from dataclasses import dataclass


@dataclass(frozen=True)
class ScraperConfig:
    http_limits_max_connections: int = 100
    http_limits_max_keepalive_connections: int = 20
    max_retries: int = 3
    base_delay: float = 2.0
    semaphore_value: int = 5

    base_ats_fetch_semaphore = 20



DEFAULT_SCRAPER_CONFIG = ScraperConfig()
