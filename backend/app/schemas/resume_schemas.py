from pydantic import BaseModel
from typing import Dict, Optional
from app.services.resume_updators.resume_section_enum import ResumeSectionType
from app.services.resume_updators.validation_error_enum import ResumeErrorType

class ResumeChanges(BaseModel):
    SUM: Optional[str] = None
    COURSES: Optional[Dict[str, str]] = None
    EXP: Optional[Dict[str, str]] = None
    PROJ: Optional[Dict[str, str]] = None
    TECHNICAL_SKILLS: Optional[str] = None

class ResumeError(BaseModel):
    error: ResumeErrorType
    message: str
    section: ResumeSectionType