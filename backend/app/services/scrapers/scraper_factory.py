from app.services.scrapers.ats_scrapers.asbhy_scraper import AshbyScraper
from app.services.scrapers.ats_scrapers.greenhouse_scraper import GreenhouseScraper 
from app.services.scrapers.ats_scrapers.lever_scraper import LeverScraper
from app.services.scrapers.null_scraper import NullScraper
from app.services.scrapers.base_scraper import BaseScraper


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