"""
Resolve SmartRecruiters company slugs for the companies listed under the
"unknown" key of company_map.json.

Bugs fixed across iterations of this script:

1. DDG query was too loose ('company smartrecruiters', no quotes/site filter)
   -> ranked generic SmartRecruiters marketing pages first.
   Fix: quote the company name and add site:smartrecruiters.com, try a few
   phrasings and rank candidates by best position seen across all of them.

2. Verification hit a non-existent endpoint / trusted a 200 status.
   /v1/companies/{slug}/postings returns HTTP 200 with totalFound: 0 for ANY
   slug, real or fake. Fix: require totalFound > 0 AND that the identifier
   echoed back in the response matches the slug you guessed.

3. Verification proved the slug was a *real, active* SmartRecruiters
   customer, but never proved it was the RIGHT customer - an unrelated but
   real company (e.g. "Jobs for Humanity") could win just by being real.
   Fix: score candidates by name similarity to the company you searched for.

4. THIS ONE: raw character-sequence similarity (difflib ratio) is not a
   reliable signal for short company names. It confidently matched
   'deel' -> 'Dell' (0.75) and 'snyk' -> 'Sandisk' (0.55) - real companies
   that are completely unrelated to what was being searched for, just
   because they share some scattered letters. No threshold fixes this,
   because a real match and a coincidental collision land in the same
   score range for short strings.
   Fix: drop pure character-ratio scoring. Only accept an exact normalized
   match, or a clean containment relationship (one name fully inside the
   other, e.g. an abbreviation or an extra qualifier like "Technologies"),
   scaled by how much of the longer name the shorter one accounts for.
   Also fold accented characters (Montréal / Montreal, Stäubli / Staubli)
   during normalization so those don't get penalized as mismatches.

5. An unhandled exception partway through a 480-company run crashed the
   whole process, and since results were only written to disk at the very
   end, everything was lost. Fix: isolate exceptions per-company so one
   failure can't take down the batch, and checkpoint results to disk
   periodically as they come in, not just at the end.
"""

import json
import re
import time
import random
import asyncio
import unicodedata
from typing import Optional, List, Dict
from urllib.parse import urlparse

import httpx
from ddgs import DDGS

INPUT_FILE = "discover_smart_recruiters_companies/company_map.json"
FOUND_FILE = "discover_smart_recruiters_companies/smartrecruiters_companies_map.json"
NOT_FOUND_FILE = "discover_smart_recruiters_companies/smartrecruiters_not_found.json"
ERROR_FILE = "discover_smart_recruiters_companies/smartrecruiters_errors.json"

MAX_CONCURRENT = 2          # keep DDG concurrency low or it will start blocking you
MATCH_THRESHOLD = 0.4       # containment-ratio floor; exact matches always score 1.0
CHECKPOINT_EVERY = 15        # write partial results to disk this often

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

SUFFIXES = {
    "inc", "incorporated", "llc", "corp", "corporation", "co", "company",
    "ltd", "limited", "group", "holdings", "plc",
}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def strip_suffix(token: str) -> str:
    """Trim a trailing corporate suffix even when it's fused onto the word
    with no space (e.g. 'promediagroup' -> 'promedia')."""
    for suf in sorted(SUFFIXES, key=len, reverse=True):
        if token.endswith(suf) and len(token) > len(suf):
            return token[: -len(suf)]
    return token


def normalize(name: str) -> str:
    name = strip_accents(name)
    tokens = [t for t in re.findall(r"[a-z0-9]+", name.lower()) if t not in SUFFIXES]
    tokens = [strip_suffix(t) for t in tokens]
    return "".join(tokens) if tokens else re.sub(r"[^a-z0-9]", "", name.lower())


def match_score(a: str, b: str) -> float:
    """1.0 for an exact normalized match. Otherwise only credit a
    containment relationship - not raw character similarity, which
    produces deceptively high scores for short, coincidentally-overlapping
    words that are actually unrelated companies (e.g. 'deel' vs 'dell')."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if len(shorter) >= 4 and shorter in longer:
        return len(shorter) / len(longer)
    return 0.0


def guess_slug(company_name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", company_name.lower())


def slug_from_url(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url)
        if "smartrecruiters.com" not in parsed.netloc:
            return None
        parts = [p for p in parsed.path.split("/") if p]
        if not parts:
            return None
        if "companies" in parts:
            i = parts.index("companies")
            return parts[i + 1] if i + 1 < len(parts) else None
        return parts[0]
    except Exception:
        return None


def ddg_search(query: str, max_results: int) -> List[dict]:
    """One retry on timeout-flavored errors - these showed up a lot in the
    480-company run and each one silently cost that company all its DDG
    candidates."""
    for attempt in range(2):
        try:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))
        except Exception as e:
            if attempt == 0 and "time" in str(e).lower():
                time.sleep(2.0)
                continue
            print(f"   DDG error for '{query}': {e}")
            return []
    return []


def ddg_candidates(company_name: str, max_results: int = 10) -> List[str]:
    """Try a few phrasings and merge results, ranked by the best (lowest)
    position each slug reached across all of them."""
    queries = [
        f'"{company_name}" site:careers.smartrecruiters.com',
        f'{company_name} careers site:smartrecruiters.com',
        f'{company_name} site:smartrecruiters.com',
    ]
    best_rank: Dict[str, int] = {}
    for query_idx, q in enumerate(queries):
        results = ddg_search(q, max_results)
        for position, r in enumerate(results):
            slug = slug_from_url(r.get("href", ""))
            if not slug:
                continue
            score = query_idx * 100 + position
            if slug not in best_rank or score < best_rank[slug]:
                best_rank[slug] = score
        time.sleep(random.uniform(1.0, 2.0))
    return [slug for slug, _ in sorted(best_rank.items(), key=lambda kv: kv[1])]


async def verify_slug(client: httpx.AsyncClient, slug: str) -> Optional[Dict[str, str]]:
    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    try:
        resp = await client.get(url, params={"limit": 1}, headers=HEADERS, timeout=10.0)
    except httpx.RequestError:
        return None
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    if data.get("totalFound", 0) == 0 or not data.get("content"):
        return None
    company = data["content"][0].get("company", {})
    if company.get("identifier", "").lower() != slug.lower():
        return None
    return {"slug": company["identifier"], "name": company.get("name", "")}


async def resolve_company(client: httpx.AsyncClient, company_name: str, sem: asyncio.Semaphore):
    """Never let an exception here escape - one bad company must not be
    able to take down the other 479."""
    try:
        async with sem:
            candidates = [guess_slug(company_name)]
            for s in ddg_candidates(company_name):
                if s not in candidates:
                    candidates.append(s)

            best = None  # (score, slug, name)
            for slug in candidates:
                match = await verify_slug(client, slug)
                if match:
                    score = match_score(company_name, match["name"])
                    print(f"   candidate slug '{slug}': '{company_name}' vs '{match['name']}' -> score {score:.2f}")
                    if score >= MATCH_THRESHOLD and (best is None or score > best[0]):
                        best = (score, match["slug"], match["name"])
                await asyncio.sleep(random.uniform(0.5, 1.5))

        if best:
            score, slug, name = best
            print(f"   FOUND: {company_name} -> {slug} ({name}, score {score:.2f})")
            return company_name, slug, None

        print(f"   no confident match: {company_name}")
        return company_name, None, None

    except Exception as e:
        print(f"   ERROR resolving {company_name}: {e}")
        return company_name, None, str(e)


def write_outputs(found: Dict[str, str], not_found: List[str], errors: Dict[str, str]):
    with open(FOUND_FILE, "w") as f:
        json.dump(found, f, indent=2)
    with open(NOT_FOUND_FILE, "w") as f:
        json.dump(not_found, f, indent=2)
    with open(ERROR_FILE, "w") as f:
        json.dump(errors, f, indent=2)


async def main():
    with open(INPUT_FILE) as f:
        company_map = json.load(f)

    companies = []
    for value in company_map.values():
        if isinstance(value, list):
            companies.extend(value)

    if not companies:
        print("No companies under 'unknown' in company_map.json.")
        return

    print(f"Resolving {len(companies)} companies against SmartRecruiters...")

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    found: Dict[str, str] = {}
    not_found: List[str] = []
    errors: Dict[str, str] = {}

    async with httpx.AsyncClient() as client:
        tasks = [asyncio.create_task(resolve_company(client, name, sem)) for name in companies]

        done = 0
        for coro in asyncio.as_completed(tasks):
            name, slug, error = await coro
            if error:
                errors[name] = error
            elif slug:
                found[name] = slug
            else:
                not_found.append(name)

            done += 1
            if done % CHECKPOINT_EVERY == 0:
                write_outputs(found, not_found, errors)
                print(f"--- checkpoint: {done}/{len(companies)} processed, "
                      f"{len(found)} found so far ---")

    write_outputs(found, not_found, errors)
    print(f"\n{len(found)} found -> {FOUND_FILE}")
    print(f"{len(not_found)} not found -> {NOT_FOUND_FILE}")
    print(f"{len(errors)} errored -> {ERROR_FILE}")


if __name__ == "__main__":
    asyncio.run(main())