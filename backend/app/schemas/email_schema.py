# app/schemas/email.py
from pydantic import BaseModel
from datetime import datetime

class ScrapedEmail(BaseModel):
    email_id: str
    folder: str
    sender_email: str
    subject: str
    time: datetime
    body: str