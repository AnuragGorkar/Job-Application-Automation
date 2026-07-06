# app/schemas/email.py
from pydantic import BaseModel
from datetime import datetime

class ScrapedEmail(BaseModel):
    email_id: str
    folder: str  # Added to track which folder the email came from
    sender_email: str
    subject: str
    time: datetime
    body: str