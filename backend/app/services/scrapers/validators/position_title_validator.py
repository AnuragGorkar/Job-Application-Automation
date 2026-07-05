import re

from app.schemas.scraped_job import ScrapedJob
from app.services.scrapers.validators.scraped_job_validator import ScrapedJobValidator


# ==========================================
# Role Targeting (SDE / MLE / Data Science / GenAI-AI Engineering only)
# ==========================================
# Word-boundary phrase patterns -- title must match at least ONE of these.
# This avoids the old bug where a bare "ai" or "data" substring matched
# things like "maintain", "chair", "database administrator", etc.
ROLE_PATTERNS = [
    # Software / SDE
    r"\bsoftware engineer\b", r"\bsoftware developer\b", r"\bsde\b",
    r"\bbackend engineer\b", r"\bback[- ]end engineer\b",
    r"\bfull[- ]stack engineer\b", r"\bapplication engineer\b",

    # ML Engineering
    r"\bmachine learning engineer\b", r"\bml engineer\b", r"\bmle\b",
    r"\bmlops engineer\b",

    # Data Science
    r"\bdata scientist\b", r"\bdata science\b",
    r"\bapplied scientist\b",

    # GenAI / AI Engineering
    r"\bai engineer\b", r"\bgenai engineer\b", r"\bgenerative ai\b",
    r"\bllm engineer\b", r"\bnlp engineer\b", r"\bai\/ml engineer\b",
    r"\bartificial intelligence engineer\b",
]
ROLE_REGEX = re.compile("|".join(ROLE_PATTERNS), re.IGNORECASE)

# Seniority exclusions, matched as whole words/phrases so "head" doesn't
# false-positive on "Headquarters" etc.
SENIORITY_PATTERNS = [
    r"\bsenior\b", r"\bsr\.?\b", r"\blead\b", r"\bstaff\b", r"\bprincipal\b",
    r"\bmanager\b", r"\bdirector\b", r"\bhead of\b", r"\bvp\b",
    r"\bvice president\b", r"\barchitect\b",
]
SENIORITY_REGEX = re.compile("|".join(SENIORITY_PATTERNS), re.IGNORECASE)


class PositionTitleValidator(ScrapedJobValidator):
    def _do_validate(self, job: ScrapedJob) -> bool:
        try:
            if not job.title:
                return False
            if SENIORITY_REGEX.search(job.title):
                return False
            if not ROLE_REGEX.search(job.title):
                return False
        except Exception as e:
            print(f"[PositionTitleValidator] Error processing position title: {e}")
            return False

        return self.pass_to_next_validator(job)