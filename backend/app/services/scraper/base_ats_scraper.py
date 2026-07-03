import requests
from abc import abstractmethod

from app.service.scrapers.base_scraper import BaseScraper
from app.schemas.job import ScrapedJob

class BaseATSScraper(BaseScraper):
    def __init__(self, base_url, params):
        self.base_url = base_url
        self.params = params

    def build_company_url(self, company_name: str) -> str:
        # Add company name
        company_url = self.base_url + company_name

        # Add parameters
        url_params= "?"
        for key, value in self.params.items():
            url_params += key + "=" + value
        
        scrape_url = company_url + url_params

        return scrape_url
    
    @abstractmethod
    def map_to_scraped_job(self, job: dict, company_name: str) -> ScrapedJob:
        """Each platform parses JSON parameters completely differently."""
        pass
    
    def fetch(self, company_name: str) -> list[ScrapedJob]:
        url = self.build_company_url(company_name)
        jobs = []
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                for job in r.json().get('jobs', []):
                    scraped_job = self.map_to_scraped_job(job, company_name)
                    jobs.append(scraped_job)

        except Exception as e:
            print(f"Exception faced while scraping jobs from Jobs Ashby: {e}")
            pass
        return jobs
