import asyncio

from app.services.job_scrapers.ats_scrapers.asbhy_scraper import AshbyScraper
from app.services.job_scrapers.ats_scrapers.greenhouse_scraper import GreenhouseScraper
from app.services.job_scrapers.ats_scrapers.lever_scraper import LeverScraper
from app.services.job_scrapers.ats_scrapers.workday_scraper import WorkdayScraper
from app.services.job_scrapers.company_scrapers.amazon_scraper import AmazonScraper
from app.services.job_scrapers.company_scrapers.meta_scraper import MetaScraper
from app.services.job_scrapers.company_scrapers.microsoft_scraper import MicrosoftScraper
from app.services.job_scrapers.null_scraper import NullScraper


def test_scrapers_receive_and_store_job_queue():
    job_queue = asyncio.Queue()

    scrapers = [
        AshbyScraper(job_queue),
        GreenhouseScraper(job_queue),
        LeverScraper(job_queue),
        WorkdayScraper(job_queue),
        AmazonScraper(job_queue),
        MetaScraper(job_queue),
        MicrosoftScraper(job_queue),
        NullScraper(job_queue),
    ]

    for scraper in scrapers:
        assert scraper.job_queue is job_queue
