import logging

import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.core.config import get_settings
from app.core.constants import COMPANIES
from app.core.logger import setup_logging
from app.services.job_scrapers.job_scraper import JobScraper

settings = get_settings()

setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Application starting up...")
    yield 
    print("Application shutting down...")

# Create FastAPI app instance
app = FastAPI(title="Job Automation", lifespan=lifespan)


@app.get("/")
def health_check():
    logger.info("Health check requested")
    return {"environment": settings.env_state, "port": settings.be_port}


@app.get("/scrape")
async def scrape_jobs():
    logger.info("Scrape endpoint requested")
    job_scraper = JobScraper(COMPANIES)
    return await job_scraper.scrape_and_validate()

if __name__ == "__main__":
    # Run FastAPI app running in uvicorn webserver
    uvicorn.run("app.main:app", host=settings.be_host, port=settings.be_port, reload=True)
