from asyncio import Queue

from app.services.job_scrapers.ats_scrapers.asbhy_scraper import AshbyScraper
from app.services.job_scrapers.ats_scrapers.greenhouse_scraper import GreenhouseScraper 
from app.services.job_scrapers.ats_scrapers.lever_scraper import LeverScraper
from app.services.job_scrapers.company_scrapers.amazon_scraper import AmazonScraper
from app.services.job_scrapers.company_scrapers.meta_scraper import MetaScraper
from app.services.job_scrapers.company_scrapers.microsoft_scraper import MicrosoftScraper
from app.services.job_scrapers.null_scraper import NullScraper
from app.services.job_scrapers.base_scraper import BaseScraper
from app.services.job_scrapers.ats_scrapers.workday_scraper import WorkdayScraper
from app.services.job_scrapers.ats_scrapers.smart_recruiters_scraper import SmartRecruitersScraper


class ScraperFactory:
    @staticmethod
    def get_scraper(scraper_name: str, validation_queue, enrichment_queue: Queue) -> BaseScraper:
        if scraper_name == "greenhouse":
            return GreenhouseScraper(validation_queue, enrichment_queue)
        elif scraper_name == "ashby":
            return AshbyScraper(validation_queue, enrichment_queue)
        elif scraper_name == "lever":
            return LeverScraper(validation_queue, enrichment_queue)
        elif scraper_name == "workday":
            return WorkdayScraper(validation_queue, enrichment_queue)
        elif scraper_name == "smartrecruiters":
            return SmartRecruitersScraper(validation_queue, enrichment_queue)
        
        elif scraper_name == "amazon":
            return AmazonScraper(validation_queue, enrichment_queue)
        elif scraper_name == "meta":
            return MetaScraper(validation_queue, enrichment_queue)
        elif scraper_name == "microsoft":
            return MicrosoftScraper(validation_queue, enrichment_queue)
        else:
            # Returns Null object instead of None
            return NullScraper(validation_queue, enrichment_queue)