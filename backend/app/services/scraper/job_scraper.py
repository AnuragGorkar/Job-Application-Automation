import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.services.scraper.scraped_job_validator import ScrapedJobValidator
from app.schemas.scraped_job import ScrapedJob 
from app.services.scraper.base_scraper import BaseScraper

class JobScraper:
    def __init__(self, scraper_dict: dict[str, BaseScraper], validator: ScrapedJobValidator):
        self.validator = validator
        self.scraper_dict = scraper_dict
        self.job_queue = queue.Queue()
        self.valid_jobs = []
    
    def _company_scraper(self, platform_name: str, company_name: str):
        scraper = self.scraper_dict.get(platform_name)
        if not scraper:
            return

        try:
            jobs = scraper.fetch(company_name)
            if jobs:
                self.job_queue.put(jobs)
                
        except Exception as e:
            print(f"[Thread Error] Platform {platform_name}, company {company_name} failed: {e}")

    def _validation_job(self):
        while True:
            job_batch = self.job_queue.get()
            
            if job_batch is None:
                self.job_queue.task_done()
                break
            
            try:
                for job in job_batch:
                    if self.validator.validate(job):
                        self.valid_jobs.append(job)
            except Exception as e:
                print(f"Job validation error in queue: {e}")
            finally:
                self.job_queue.task_done()

    def scrape_and_validate(self, target_companies: dict[str, list[str]]) -> list[ScrapedJob]:
        self.valid_jobs = [] # Reset for new run

        # Start background consumer thread
        consumer_thread = threading.Thread(target=self._validation_job, daemon=True)
        consumer_thread.start()

        # Flatten targets into individual tasks: [("ashby", "reddit"), ("lever", "netflix")]
        tasks = []
        for platform, companies in target_companies.items():
            for company in companies:
                tasks.append((platform, company))

        # Start thread pool producers
        workers = min(15, len(tasks)) or 1
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(self._company_scraper, plat, comp) 
                for plat, comp in tasks
            ]
            
            for future in as_completed(futures):
                pass 

        self.job_queue.put(None)
        
        consumer_thread.join()

        print(f"[Complete] Validation finished. Returning {len(self.valid_jobs)} matching jobs.")
        return self.valid_jobs