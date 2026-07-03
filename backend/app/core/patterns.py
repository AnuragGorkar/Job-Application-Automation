import re
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

# ==========================================
# US-Only Location Targeting
# ==========================================
# Explicit country-level indicators
US_COUNTRY_PATTERNS = [r"\bunited states\b", r"\bu\.s\.a?\.?\b", r"\busa\b", r"\bus\b"]

# US state abbreviations + a handful of major tech-hub cities, all matched
# as whole words/tokens (so "ca" only matches ", CA" not "canada" or
# "scale"). State names spelled out are also included for boards that
# write full names.
US_STATE_ABBR = [
    "al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il","in",
    "ia","ks","ky","la","me","md","ma","mi","mn","ms","mo","mt","ne","nv",
    "nh","nj","nm","ny","nc","nd","oh","ok","or","pa","ri","sc","sd","tn",
    "tx","ut","vt","va","wa","wv","wi","wy","dc",
]
US_CITIES = [
    "san francisco", "new york", "seattle", "austin", "raleigh", "durham",
    "boston", "chicago", "los angeles", "san jose", "san diego", "denver",
    "atlanta", "miami", "dallas", "houston", "washington", "portland",
    "pittsburgh", "detroit", "minneapolis", "phoenix", "charlotte",
    "nashville", "salt lake city", "philadelphia", "columbus",
]
US_LOCATION_PATTERNS = (
    US_COUNTRY_PATTERNS
    + [rf"\b{abbr}\b" for abbr in US_STATE_ABBR]
    + [rf"\b{re.escape(city)}\b" for city in US_CITIES]
)
US_LOCATION_REGEX = re.compile("|".join(US_LOCATION_PATTERNS), re.IGNORECASE)

# Anything explicitly tagged as international gets excluded outright, even
# if it happens to also contain a US-looking token (rare, but cheap safety net)
INTL_PATTERNS = [
    r"\beurope\b", r"\buk\b", r"\bunited kingdom\b", r"\blondon\b",
    r"\bindia\b", r"\bgermany\b", r"\bemea\b", r"\bapac\b", r"\bcanada\b",
    r"\btoronto\b", r"\bireland\b", r"\bsingapore\b", r"\baustralia\b",
    r"\blatam\b", r"\bmexico\b", r"\bbrazil\b",
]
INTL_REGEX = re.compile("|".join(INTL_PATTERNS), re.IGNORECASE)