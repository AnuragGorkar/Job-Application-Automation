from datetime import datetime
from pydantic import BaseModel

class ScrapedJob(BaseModel):
    url: str
    company: str
    title: str
    description: str 
    location: str
    posted_at: datetime
    platform: str