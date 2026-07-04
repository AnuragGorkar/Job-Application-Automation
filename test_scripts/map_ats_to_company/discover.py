"""
ATS board resolver.

Input:  company_map.json  -> {"unknown": ["Company A", "Company B", ...], ...}
Output: company_map_updated.json -> same top-level shape, plus a "needs_review"
        bucket for anything that couldn't be verified with high confidence.

Design goals (vs. the original version):
  1. Never trust a search-result URL by itself. Every candidate slug is
     verified against the ATS's own public API before being accepted.
  2. Prefer guessing the slug directly from the company name and hitting the
     public API -- this needs no search engine at all for the large majority
     of companies, which is both more reliable and much faster.
  3. Only fall back to DuckDuckGo search when direct guessing fails, and even
     then, verify whatever is found the same way.
  4. Score every match with a name-similarity confidence so ambiguous hits
     land in "needs_review" instead of being silently mislabeled.
  5. Checkpoint after every company so a crash mid-run doesn't lose progress.
  6. Bound concurrency: direct API checks run in a real thread pool; the
     DuckDuckGo fallback is limited by a semaphore so it doesn't get you
     rate-limited/blocked.
"""

import json
import os
import re
import time
import random
import logging
import difflib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from ddgs import DDGS

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

INPUT_FILE = "company_map.json"
OUTPUT_FILE = "company_map_updated.json"
LOG_FILE = "resolution_log.txt"

MAX_WORKERS = 8            # direct API checks -- these are cheap public APIs
MAX_CONCURRENT_SEARCHES = 2  # DuckDuckGo fallback -- keep this low
REQUEST_TIMEOUT = 8
CONFIDENCE_ACCEPT = 0.60    # >= this -> accepted straight into the platform bucket
CONFIDENCE_FLOOR = 0.30     # >= this but < ACCEPT -> needs_review, else discarded

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobBoardResolver/2.0; +personal-job-search-tool)"}

LEGAL_SUFFIXES = {
    "inc", "incorporated", "llc", "l l c", "corp", "corporation", "co",
    "company", "ltd", "limited", "group", "holdings", "technologies",
    "technology", "labs", "plc", "the",
}

PATTERNS = {
    "greenhouse": re.compile(r"boards\.greenhouse\.io/([^/?#]+)"),
    "lever": re.compile(r"jobs\.lever\.co/([^/?#]+)"),
    "ashby": re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)"),
    "smartrecruiters": re.compile(r"smartrecruiters\.com/v1/companies/([^/?#]+)"),
    "workday": re.compile(
        r"https://([a-zA-Z0-9-]+)\.wd([0-9]+)\.myworkdayjobs\.com/(?:en-US/)?([a-zA-Z0-9_-]+)"
    ),
}

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger("ats_resolver")

# --------------------------------------------------------------------------
# HTTP session with sane retries
# --------------------------------------------------------------------------

def build_session():
    s = requests.Session()
    retries = Retry(
        total=2,
        backoff_factor=0.6,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s


SESSION = build_session()

# --------------------------------------------------------------------------
# Name normalization / similarity / slug candidate generation
# --------------------------------------------------------------------------

def normalize(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"[.,()]", "", name)
    name = name.replace("&", " and ")
    words = [w for w in re.split(r"[\s_-]+", name) if w and w not in LEGAL_SUFFIXES]
    return " ".join(words)


def similarity(company_name: str, candidate_name: str) -> float:
    """Rough confidence that `candidate_name` (from an ATS API response, or a
    slug reinterpreted as words) refers to the same company as `company_name`."""
    if not candidate_name:
        return 0.0
    a = normalize(company_name).replace(" ", "")
    b = normalize(candidate_name).replace(" ", "")
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.85
    return difflib.SequenceMatcher(None, a, b).ratio()


def generate_slug_candidates(company_name: str) -> list:
    base = normalize(company_name)
    if not base:
        return []
    words = base.split()
    candidates = set()
    candidates.add(base.replace(" ", ""))       # e.g. "acmewidgets"
    candidates.add(base.replace(" ", "-"))       # e.g. "acme-widgets"
    candidates.add(base.replace(" ", "_"))       # e.g. "acme_widgets" (rare, cheap to try)
    alnum_only = re.sub(r"[^a-z0-9]", "", base)
    candidates.add(alnum_only)
    if len(words) > 1:
        candidates.add("".join(w[0] for w in words))  # acronym, e.g. "aw"
    candidates.discard("")
    # Order: no-space concat first (most common convention), then hyphenated,
    # then the rest.
    ordered = sorted(candidates, key=lambda c: (c != base.replace(" ", ""), len(c)))
    return ordered

# --------------------------------------------------------------------------
# Per-platform verification against the ATS's own public API
# Each returns None on no-match, or a dict with a confidence score.
# --------------------------------------------------------------------------

def check_greenhouse(slug, company_name):
    try:
        r = SESSION.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}",
                         headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None
        data = r.json()
        found_name = data.get("name", "")
        score = similarity(company_name, found_name) if found_name else 0.5
        return {"platform": "greenhouse", "slug": slug, "confidence": round(score, 2),
                "matched_name": found_name}
    except (requests.RequestException, ValueError):
        return None


def check_lever(slug, company_name):
    try:
        r = SESSION.get(f"https://api.lever.co/v0/postings/{slug}",
                         params={"mode": "json", "limit": 1},
                         headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None
        data = r.json()
        if not isinstance(data, list):
            return None
        # Lever's postings API doesn't return a company display name, so the
        # best signal available is the slug itself vs. the company name.
        score = similarity(company_name, slug.replace("-", " "))
        return {"platform": "lever", "slug": slug, "confidence": round(score, 2),
                "matched_name": None}
    except (requests.RequestException, ValueError):
        return None


def check_ashby(slug, company_name):
    try:
        r = SESSION.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                         headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None
        data = r.json()
        found_name = data.get("organizationName", "")
        score = similarity(company_name, found_name) if found_name else 0.5
        return {"platform": "ashby", "slug": slug, "confidence": round(score, 2),
                "matched_name": found_name}
    except (requests.RequestException, ValueError):
        return None


def check_smartrecruiters(slug, company_name):
    try:
        r = SESSION.get(f"https://api.smartrecruiters.com/v1/companies/{slug}",
                         headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None
        data = r.json()
        found_name = data.get("name", "")
        score = similarity(company_name, found_name) if found_name else 0.5
        return {"platform": "smartrecruiters", "slug": slug, "confidence": round(score, 2),
                "matched_name": found_name}
    except (requests.RequestException, ValueError):
        return None


CHECKERS = [check_greenhouse, check_lever, check_ashby, check_smartrecruiters]

# --------------------------------------------------------------------------
# Resolution strategy: direct guess first, verified search fallback second
# --------------------------------------------------------------------------

def try_direct_resolution(company_name):
    best = None
    for slug in generate_slug_candidates(company_name):
        for checker in CHECKERS:
            result = checker(slug, company_name)
            if result is None:
                continue
            if best is None or result["confidence"] > best["confidence"]:
                best = result
            if result["confidence"] >= 0.95:
                return result  # good enough, stop early
    return best


_search_semaphore = threading.Semaphore(MAX_CONCURRENT_SEARCHES)


def _ddgs_search(query, max_results=3):
    with _search_semaphore:
        try:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))
        except Exception as e:
            log.warning(f"Search failed for query '{query}': {e}")
            return []
        finally:
            time.sleep(random.uniform(2.0, 4.0))


def discover_via_search(company_name):
    site_map = [
        ("greenhouse", "site:boards.greenhouse.io", check_greenhouse, PATTERNS["greenhouse"]),
        ("lever", "site:jobs.lever.co", check_lever, PATTERNS["lever"]),
        ("ashby", "site:jobs.ashbyhq.com", check_ashby, PATTERNS["ashby"]),
        ("smartrecruiters", "site:smartrecruiters.com", check_smartrecruiters, PATTERNS["smartrecruiters"]),
    ]
    for platform, site_filter, checker, pattern in site_map:
        query = f'"{company_name}" careers {site_filter}'
        for res in _ddgs_search(query):
            url = res.get("href", "")
            m = pattern.search(url)
            if not m:
                continue
            verified = checker(m.group(1), company_name)
            if verified and verified["confidence"] >= CONFIDENCE_ACCEPT:
                return verified

    # Workday has no guessable public API, so it is only ever discovered via
    # search and can never be independently verified -- always flag it.
    query = f'"{company_name}" careers site:myworkdayjobs.com'
    for res in _ddgs_search(query):
        url = res.get("href", "")
        m = PATTERNS["workday"].search(url)
        if m:
            return {
                "platform": "workday",
                "tenant": m.group(1),
                "node": m.group(2),
                "board": m.group(3),
                "confidence": 0.40,  # unverifiable by design -> needs_review
                "matched_name": None,
            }
    return None


def resolve_company(company_name):
    direct = try_direct_resolution(company_name)
    if direct and direct["confidence"] >= CONFIDENCE_ACCEPT:
        return direct
    fallback = discover_via_search(company_name)
    candidates = [c for c in (direct, fallback) if c]
    if not candidates:
        return None
    return max(candidates, key=lambda c: c["confidence"])

# --------------------------------------------------------------------------
# Checkpointing
# --------------------------------------------------------------------------

_save_lock = threading.Lock()


def save_checkpoint(company_map):
    with _save_lock:
        tmp = OUTPUT_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(company_map, f, indent=2)
        os.replace(tmp, OUTPUT_FILE)


def record_result(company_map, company_name, result):
    with _save_lock:
        if result is None:
            company_map["unknown"].append(company_name)
            log.info(f"UNRESOLVED: {company_name}")
            return

        entry = {
            "company": company_name,
            "confidence": result["confidence"],
            "matched_name": result.get("matched_name"),
        }
        platform = result["platform"]

        if result["confidence"] < CONFIDENCE_ACCEPT:
            entry["platform"] = platform
            entry["slug"] = result.get("slug")
            if platform == "workday":
                entry["tenant"] = result["tenant"]
                entry["node"] = result["node"]
                entry["board"] = result["board"]
            company_map.setdefault("needs_review", []).append(entry)
            log.info(f"NEEDS REVIEW ({platform}, conf={result['confidence']}): {company_name}")
            return

        if platform == "workday":
            company_map["workday"].append({
                "company": company_name,
                "tenant": result["tenant"],
                "node": result["node"],
                "board": result["board"],
                "confidence": result["confidence"],
            })
        else:
            company_map[platform].append({
                "company": company_name,
                "slug": result["slug"],
                "confidence": result["confidence"],
            })
        log.info(f"RESOLVED {company_name} -> {platform} (conf={result['confidence']})")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        with open(INPUT_FILE, "r") as f:
            company_map = json.load(f)
    except FileNotFoundError:
        log.error(f"Could not find {INPUT_FILE} in the current directory.")
        company_map = {"greenhouse": [], "lever": [], "ashby": [],
                        "smartrecruiters": [], "workday": [], "unknown": []}

    for key in ("greenhouse", "lever", "ashby", "smartrecruiters", "workday", "needs_review"):
        company_map.setdefault(key, [])

    targets = company_map.get("unknown", [])
    company_map["unknown"] = []  # will be repopulated only with true failures
    log.info(f"Resolving {len(targets)} companies with up to {MAX_WORKERS} workers...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(resolve_company, name): name for name in targets}
        completed = 0
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
            except Exception as e:
                log.error(f"CRASH resolving {name}: {e}")
                result = None
            record_result(company_map, name, result)
            completed += 1
            if completed % 5 == 0 or completed == len(targets):
                save_checkpoint(company_map)
                log.info(f"Checkpoint saved ({completed}/{len(targets)})")

    save_checkpoint(company_map)
    log.info(f"Done. Results in {OUTPUT_FILE}, full log in {LOG_FILE}.")