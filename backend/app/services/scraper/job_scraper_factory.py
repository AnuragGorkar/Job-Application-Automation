from app.services.scraper.base_scraper import BaseScraper, NullScraper
from app.services.scraper.ats_scraper import GreenhouseScraper, AshbyScraper, LeverScraper

class JobScrapperFactory():
    def __init__(self):
        pass

    def getScraper(scraper_name: str) -> BaseScraper:
        if scraper_name == "greenhouse":
            return GreenhouseScraper()
        elif scraper_name == "ashby":
            return AshbyScraper()
        elif scraper_name == "lever":
            return LeverScraper()
        elif scraper_name == "smartrecruiters":
            return 
        else:
            return NullScraper()