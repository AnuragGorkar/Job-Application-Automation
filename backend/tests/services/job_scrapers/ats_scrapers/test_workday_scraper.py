import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.ats_scrapers.workday_scraper import WorkdayScraper
from app.services.job_scrapers.scraper_config import ScraperConfig

# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def mock_workday_config(tmp_path):
    """Creates a temporary JSON config file matching the user's structure."""
    config_data = {
        "zelis_ZelisCareers": {
            "company_name": "zelis",
            "api_url": "https://zelis.wd1.myworkdayjobs.com/wday/cxs/zelis/ZelisCareers/jobs",
            "portal_id": "ZelisCareers",
            "server": "wd1",
            "tenant": "zelis",
            "discovery": "duckduckgo"
        },
        "kyndryl_KyndrylProfessionalCareers": {
            "company_name": "kyndryl",
            "api_url": "https://kyndryl.wd5.myworkdayjobs.com/wday/cxs/kyndryl/KyndrylProfessionalCareers/jobs",
            "portal_id": "KyndrylProfessionalCareers",
            "server": "wd5",
            "tenant": "kyndryl",
            "discovery": "duckduckgo"
        }
    }
    
    # Write to a temporary file
    config_file = tmp_path / "test_workday_config.json"
    config_file.write_text(json.dumps(config_data))
    return str(config_file)

@pytest.fixture
def scraper(mock_workday_config, monkeypatch):
    """Initializes the scraper with dummy queues and the temporary config."""
    # Monkeypatch the class constant so it points to our temporary test JSON
    monkeypatch.setattr(WorkdayScraper, "CONFIG_FILE_PATH", mock_workday_config)
    
    validation_queue = asyncio.Queue()
    enrichment_queue = asyncio.Queue()
    config = ScraperConfig(max_retries=1, base_delay=0.1) # Fast retries for testing
    
    return WorkdayScraper(validation_queue, enrichment_queue, config)


# ==============================================================================
# 1. PURE LOGIC TESTS (No HTTP Mocking Needed)
# ==============================================================================

def test_parse_workday_date(scraper):
    """Tests the datetime conversion for various Workday formats."""
    now = datetime.now(timezone.utc)
    
    # Test "Today"
    today_parsed = datetime.fromisoformat(scraper._parse_workday_date("Posted Today"))
    assert (now - today_parsed).total_seconds() < 5  # Basically identical
    
    # Test "Yesterday"
    yesterday_parsed = datetime.fromisoformat(scraper._parse_workday_date("Posted Yesterday"))
    assert yesterday_parsed.date() == (now - timedelta(days=1)).date()
    
    # Test "30+ Days Ago"
    days_ago_parsed = datetime.fromisoformat(scraper._parse_workday_date("Posted 30+ Days Ago"))
    assert days_ago_parsed.date() == (now - timedelta(days=30)).date()
    
    # Test Garbage / None
    garbage_parsed = datetime.fromisoformat(scraper._parse_workday_date("Garbage String"))
    assert (now - garbage_parsed).total_seconds() < 5 # Defaults to now

def test_map_to_scraped_job(scraper):
    """Tests Phase 1 mapping of summary data."""
    raw_job = {
        "title": "Software Engineer",
        "externalPath": "/Engineering/REQ-123",
        "locationsText": "Remote, US",
        "postedOn": "Posted 2 Days Ago"
    }
    company_config = scraper.workday_configs["zelis_ZelisCareers"]
    
    mapped_job = scraper.map_to_scraped_job(raw_job, "zelis_ZelisCareers", company_config)
    
    assert mapped_job.title == "Software Engineer"
    assert mapped_job.location == "Remote, US"
    assert mapped_job.platform == "Workday"
    assert mapped_job.company == "zelis_ZelisCareers"
    # Ensure URL is built perfectly from tenant, server, and portal_id
    assert mapped_job.url == "https://zelis.wd1.myworkdayjobs.com/en-US/ZelisCareers/Engineering/REQ-123"
    assert mapped_job.description == ""


# ==============================================================================
# 2. HTTP BOUNDARY TESTS (Phase 1: Fetching)
# ==============================================================================

@pytest.mark.asyncio
async def test_scrape_single_company_success(scraper, httpx_mock: HTTPXMock):
    """Tests that Phase 1 correctly fetches summary jobs and queues them."""
    company_name = "zelis_ZelisCareers"
    config = scraper.workday_configs[company_name]
    
    # Setup the fake Workday Response
    mock_response = {
        "total": 1,
        "jobPostings": [
            {
                "title": "Backend Dev",
                "externalPath": "/IT/REQ-999",
                "locationsText": "Dallas, TX",
                "postedOn": "Posted Today"
            }
        ]
    }
    
    # Tell pytest-httpx to intercept the POST request to the config's api_url
    httpx_mock.add_response(
        method="POST", 
        url=config["api_url"], 
        json=mock_response, 
        status_code=200
    )
    
    async with httpx.AsyncClient() as client:
        semaphore = asyncio.Semaphore(1)
        await scraper._scrape_single_company(company_name, config, client, semaphore)
        
    # Verify the job was pushed to the validation queue
    assert scraper.validation_queue.qsize() == 1
    
    queued_job = await scraper.validation_queue.get()
    assert queued_job.title == "Backend Dev"
    assert "zelis" in queued_job.url


# ==============================================================================
# 3. HTTP BOUNDARY TESTS (Phase 2: Enrichment)
# ==============================================================================

@pytest.mark.asyncio
async def test_enrich_success(scraper, httpx_mock: HTTPXMock):
    """Tests that Phase 2 correctly fetches and appends the deep HTML description."""
    
    # Create a dummy Phase 1 job
    summary_job = ScrapedJob(
        title="Test Job",
        location="USA",
        description="Initial summary...",
        posted_at=datetime.now(),
        url="https://kyndryl.wd5.myworkdayjobs.com/en-US/KyndrylProfessionalCareers/job/REQ-1",
        company="kyndryl_KyndrylProfessionalCareers",
        platform="Workday"
    )
    
    # Setup the fake Workday HTML response nested in JSON
    mock_detail_response = {
        "jobPostingInfo": {
            "jobDescription": "<p>This is the full job description.</p>"
        }
    }
    
    # Intercept the GET request to the hidden API endpoint
    # Note how the URL transforms from /en-US/ to /wday/cxs/kyndryl/
    expected_api_url = "https://kyndryl.wd5.myworkdayjobs.com/wday/cxs/kyndryl/KyndrylProfessionalCareers/job/REQ-1"
    
    httpx_mock.add_response(
        method="GET",
        url=expected_api_url,
        json=mock_detail_response,
        status_code=200
    )
    
    # Run the enrichment
    enriched_job = await scraper.enrich(summary_job.company, summary_job)
    
    # Verify the description was parsed, cleaned of HTML tags, and appended
    assert "This is the full job description." in enriched_job.description
    assert "Initial summary..." in enriched_job.description

@pytest.mark.asyncio
async def test_enrich_waf_block_handling(scraper, httpx_mock: HTTPXMock):
    """Tests that Phase 2 gracefully handles a 429 Rate Limit from the WAF."""
    
    summary_job = ScrapedJob(
        title="Blocked Job",
        location="USA",
        description="",
        posted_at=datetime.now(),
        url="https://zelis.wd1.myworkdayjobs.com/en-US/ZelisCareers/job/REQ-2",
        company="zelis_ZelisCareers",
        platform="Workday"
    )
    
    # Intercept the request and force a 429 Too Many Requests response
    expected_api_url = "https://zelis.wd1.myworkdayjobs.com/wday/cxs/zelis/ZelisCareers/job/REQ-2"
    httpx_mock.add_response(method="GET", url=expected_api_url, status_code=429)
    
    # Run the enrichment
    enriched_job = await scraper.enrich(summary_job.company, summary_job)
    
    # Verify it didn't crash and properly appended the failure note
    assert "[Description fetch failed due to rate limit]" in enriched_job.description