# import asyncio
# from typing import Optional

# import httpx
# import logging

# from backend.app.schemas.scraped_job import ScrapedJob
# from backend.app.services.job_scrapers.base_scraper import BaseScraper


# logger = logging.getLogger(__name__)

# class AmazonScraper(BaseScraper):
    
#     def __init__(self):
#         self.company_name = "Amazon"
#         self.AMAZON_JOBS_URL = "https://www.amazon.jobs/en-gb/search?offset=0&result_limit=10&sort=recent&category%5B%5D=software-development&job_type%5B%5D=Full-Time&country%5B%5D=USA"

#         self.AMAZON_HEADERS = {
#             "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
#             "Accept-Encoding": "gzip, deflate"
#         }

#         self.BATCH_LIMIT = 100
        
#         self.parsed_url = urlparse(self.AMAZON_JOBS_URL.replace("/search?", "/search.json?"))
#         self.query_params = parse_qs(self.parsed_url.query)
   
#     def _build_query_url(self, limit, offset) -> str:
#         temp_query_params = self.query_params

#         temp_query_params['result_limit'] = [str(limit)]
#         temp_query_params['offset'] = [str(offset)]

#         temp_query = urlencode(temp_query_params, doseq=True)
#         query_url = urlunparse(self.parsed_url._replace(query=temp_query))

#         return query_url

#     async def _fetch_hits_count(self) -> int:
#         fetch_hits_url = self._build_query_url(1, 0)

#         try:
#             async with httpx.AsyncClient() as client:
#                 r = await client.get(fetch_hits_url, headers=self.headers, timeout=10)

#                 if r.status_code == 200:
#                     data = r.json()
#                     return data.get('hits', 0)
#                 elif r.status_code in [429, 500, 502, 503, 504]:
#                     logger.warning(f"Rate limit/Server error {r.status_code} for AMAZON")
#                 else:
#                     logger.error(f"Permanent failure status {r.status_code} for AMAZON")  
#                 return 0
                  
#         except (httpx.ReadTimeout, httpx.ConnectTimeout) as t_err:
#             logger.warning(f"Timeout error getting hit count for AMAZON: {t_err}")
#             return 0
#         except httpx.RequestError as req_err:
#             logger.error(f"Network request error for AMAZON: {req_err}")
#             return 0
#         except Exception as e: 
#             logger.error("Error getting AMAZON hit count: {e}")
#             return 0

#     def map_to_scraped_job(self, job: dict, company_name: str) -> Optional[ScrapedJob]:        
#         loc_data = job.get('location') or {}
#         loc_name = loc_data.get('name') if isinstance(loc_data, dict) else None

#         if not title or not url or not loc_name:
#             return None

#         return ScrapedJob(
#             title=job['title'],
#             location=loc_name,
#             description=job["description"],
#             posted_at=job.get('posted_at'),
#             url=job.get('url'),
#             company=company_name,
#             platform=self.company_name
#         )
    
#     def _get_scraped_job_object(self, job) -> Optional[ScrapedJob]:
#         job_dict = dict()

#         posted_date_str = job.get('posted_date', '')
#         job_dict['posted_at'] = datetime.strptime(posted_date_str, "%B %d, %Y")

#         job_id = str(job.get('id', ''))
#         job_path = job.get('job_path', f"/jobs/{job_id}")
#         job_dict['url'] = f"https://www.amazon.jobs{job_path}"

#         company_name = job.get('company_name', 'Amazon')
#         business_cat = job.get('business_category', 'N/A')
#         city = job.get('city', 'N/A')

#         raw_desc = f"Company: {company_name}\n"
#         raw_desc += f"City: {city}\n"
#         raw_desc += f"Business Category: {business_cat}\n\n"
#         raw_desc += f"### Description\n{job.get('description', '')}\n\n"

#         if job.get('basic_qualifications'):
#             raw_desc += f"### Basic Qualifications\n{job.get('basic_qualifications')}"

#         job_dict["description"] = BeautifulSoup(raw_desc, 'html.parser').get_text(separator='\n').strip()

#         return self.map_to_scraped_job(job_dict, self.company_name)

#     async def _fetch_batch(self, offset) -> list[ScrapedJob]:
#         batch_url = self._build_query_url(self.BATCH_LIMIT, offset)
#         jobs = []

#         max_retries = 3
#         base_delay = 2.0 
        
#         for attempt in range(max_retries):
#             current_timeout = httpx.Timeout(12.0 + (attempt * 10.0), connect=5.0)
            
#             try:
#                 async with httpx.AsyncClient() as client:
#                     r = await client.get(batch_url, timeout=current_timeout)
                
#                 if r.status_code == 200:
#                     data = r.json()
#                     data_jobs_list = data.get('jobs', [])

#                     for job in data_jobs_list:
#                         scraped_job_obj = _get_scraped_job_object(job)
                    
#                     for job in raw_jobs:
#                         try:
#                             scraped_job = self.map_to_scraped_job(job, company_name)
#                             if scraped_job:
#                                 jobs.append(scraped_job)
#                         except Exception as map_err:
#                             logger.warning(f"Map error for AMAZON: {map_err}")
#                     return jobs 
                    
#                 elif r.status_code in [429, 500, 502, 503, 504]:
#                     logger.warning(f"Rate limit/Server error {r.status_code} for AMAZON. Retrying...")
#                 else:
#                     logger.error(f"Permanent failure status {r.status_code} for AMAZON.")
#                     return []

#             except (httpx.ReadTimeout, httpx.ConnectTimeout) as t_err:
#                 logger.warning(f"Timeout on attempt {attempt + 1} for AMAZON: {t_err}")
#             except httpx.RequestError as req_err:
#                 logger.error(f"Network request error for AMAZON: {req_err}")
#                 return []

#             if attempt < max_retries - 1:
#                 delay = (base_delay * (2 ** attempt)) * random.uniform(0.5, 1.5)
#                 logger.info(f"Backing off for {delay:.2f} seconds before retrying AMAZON...")
#                 await asyncio.sleep(delay)

#         logger.error(f"All {max_retries} retry attempts failed for AMAZON batch.")
#         return []
    