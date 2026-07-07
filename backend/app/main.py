import logging

import uvicorn
from fastapi import FastAPI

from app.core.config import settings
from app.core.constants import COMPANIES
from app.core.logger import setup_logging
from app.services.job_scrapers.job_scraper import JobScraper

setup_logging()
logger = logging.getLogger(__name__)

# Create FastAPI app instance
app = FastAPI(title="Job Automation")


@app.get("/")
def health_check():
    logger.info("Health check requested")
    return {"environment": settings.env, "port": settings.port}


@app.get("/scrape")
async def scrape_jobs():
    logger.info("Scrape endpoint requested")
    job_scraper = JobScraper(COMPANIES)
    return await job_scraper.scrape_and_validate()


@app.on_event("startup")
async def startup_event():
    logger.info("Application starting up")


if __name__ == "__main__":
    # Run FastAPI app running in uvicorn webserver
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=True)
