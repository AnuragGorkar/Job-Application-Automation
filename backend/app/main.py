import uvicorn
from fastapi import FastAPI

from app.core.config import settings
from app.services.scrapers.job_scraper import JobScraper
from app.core.constants import COMPANIES



# Create FastAPI app instance
app = FastAPI(title="Job Automation")

@app.get("/")
def health_check():
    return {"environment": settings.env, "port": settings.port}

@app.get("/scrape")
async def scrape_jobs():
    print("started scraping")
    job_scraper = JobScraper(COMPANIES)
    return await job_scraper.scrape_and_validate()

if __name__ == "__main__":
    # Run FastAPI app running in uvicorn webserver
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=True)