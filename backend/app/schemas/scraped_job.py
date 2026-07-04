import logging
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ScrapedJob(BaseModel):
    title: str
    location: str
    posted_at: Optional[datetime]
    url: str
    company: str
    platform: str