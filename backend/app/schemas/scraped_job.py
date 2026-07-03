from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class ScrapedJob(BaseModel):
    title: str
    location: str
    posted_at: Optional[datetime]
    url: str
    company: str
    platform: str