from app.services.job_scrapers.ats_scrapers.asbhy_scraper import AshbyScraper
from app.services.job_scrapers.ats_scrapers.greenhouse_scraper import GreenhouseScraper 
from app.services.job_scrapers.ats_scrapers.lever_scraper import LeverScraper
from app.services.job_scrapers.null_scraper import NullScraper
from app.services.job_scrapers.base_scraper import BaseScraper


class ScraperFactory:
    @staticmethod
    def get_scraper(scraper_name: str) -> BaseScraper:
        if scraper_name == "greenhouse":
            return GreenhouseScraper()
        elif scraper_name == "ashby":
            return AshbyScraper()
        elif scraper_name == "lever":
            return LeverScraper()
        else:
            # Returns Null object instead of None
            return NullScraper()