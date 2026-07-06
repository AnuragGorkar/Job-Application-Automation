from enum import Enum

class ResumeSectionType(str, Enum):
    SUMMARY = "SUM"
    COURSES = "COURSES"
    EXPERIENCE = "EXP"
    PROJECTS = "PROJ"
    SKILLS = "TECHNICAL_SKILLS"