from enum import Enum

class ResumeErrorType(str, Enum):
    INVALID_LATEX = "invalid_latex"
    TEXT_TOO_LONG = "text_too_long"
    MISSING_SECTION = "missing_section"
    INVALID_FORMAT = "invalid_format"