import asyncio
import json
import random
import httpx

with open("all_ats_slugs_verify/company_slugs.json", "r", encoding="utf-8") as file:
    all_slugs = json.load(file)

CONCURRENCY_LIMITS = {
    "smartrecruiters": 5,
    "greenhouse": 8,
    "lever": 8,
    "ashby": 8,
}

MAX_RETRIES = 3
BASE_BACKOFF = 1.5  # seconds, exponential

# Default httpx UA gets flagged by WAFs on these platforms — use a normal browser UA
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


async def fetch_with_retry(client: httpx.AsyncClient, url: str, params=None):
    """Returns (response, None) on success, or (None, reason_string) on failure."""
    last_reason = "unknown_error"
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = await client.get(url, params=params)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
            last_reason = f"network_error:{type(e).__name__}"
        else:
            if response.status_code == 200:
                return response, None
            if response.status_code == 404:
                return None, "not_found"          # not retryable, real answer
            if response.status_code in (429, 500, 502, 503, 504):
                last_reason = f"http_{response.status_code}"   # retryable
            else:
                return None, f"http_{response.status_code}"    # not retryable

        if attempt < MAX_RETRIES:
            await asyncio.sleep(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 0.5))

    return None, last_reason


async def validate_smartrecruiters(slug, client, semaphore):
    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    async with semaphore:
        await asyncio.sleep(random.uniform(0, 0.2))
        response, reason = await fetch_with_retry(client, url, {"limit": 1})
        if response is None:
            return slug, False, reason
        try:
            data = response.json()
        except Exception:
            return slug, False, "bad_json"
        return (slug, True, None) if data.get("totalFound", 0) > 0 else (slug, False, "zero_jobs")


async def validate_greenhouse(slug, client, semaphore):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    async with semaphore:
        await asyncio.sleep(random.uniform(0, 0.2))
        response, reason = await fetch_with_retry(client, url)
        if response is None:
            return slug, False, reason
        try:
            data = response.json()
        except Exception:
            return slug, False, "bad_json"
        ok = isinstance(data, dict) and len(data.get("jobs", [])) > 0
        return (slug, True, None) if ok else (slug, False, "zero_jobs")


async def validate_lever(slug, client, semaphore):
    url = f"https://api.lever.co/v0/postings/{slug}"
    async with semaphore:
        await asyncio.sleep(random.uniform(0, 0.2))
        response, reason = await fetch_with_retry(client, url, {"mode": "json"})
        if response is None:
            return slug, False, reason
        try:
            data = response.json()
        except Exception:
            return slug, False, "bad_json"
        ok = isinstance(data, list) and len(data) > 0
        return (slug, True, None) if ok else (slug, False, "zero_jobs")


async def validate_ashby(slug, client, semaphore):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    async with semaphore:
        await asyncio.sleep(random.uniform(0, 0.2))
        response, reason = await fetch_with_retry(client, url)
        if response is None:
            return slug, False, reason
        try:
            data = response.json()
        except Exception:
            return slug, False, "bad_json"
        ok = isinstance(data, dict) and len(data.get("jobs", [])) > 0
        return (slug, True, None) if ok else (slug, False, "zero_jobs")


async def process_board(board_name, slugs, client):
    total = len(slugs)
    print(f"\n🚀 [{board_name}] Validating {total} slugs...")
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMITS.get(board_name, 5))
    validator_map = {
        "smartrecruiters": validate_smartrecruiters,
        "greenhouse": validate_greenhouse,
        "lever": validate_lever,
        "ashby": validate_ashby,
    }
    validator_func = validator_map[board_name]
    tasks = [validator_func(slug, client, semaphore) for slug in slugs]

    valid, failed = [], []
    reason_counts = {}
    completed = 0

    for task in asyncio.as_completed(tasks):
        slug, is_valid, reason = await task
        if is_valid:
            valid.append(slug)
        else:
            failed.append({"slug": slug, "reason": reason})
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        completed += 1
        if completed % 200 == 0 or completed == total:
            print(f"   ⏳ [{board_name}] {completed}/{total}")

    print(f"✅ [{board_name}] Active: {len(valid)} | Failed: {len(failed)}")
    print(f"   Failure reasons: {reason_counts}")
    return valid, failed


async def main():
    final_valid, final_failed = {}, {}
    limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
    timeout = httpx.Timeout(20.0, connect=10.0)

    async with httpx.AsyncClient(limits=limits, timeout=timeout, headers=HEADERS) as client:
        for board_name, slugs in all_slugs.items():
            valid, failed = await process_board(board_name, slugs, client)
            final_valid[board_name] = valid
            final_failed[board_name] = failed

    with open("all_ats_slugs_verify/verified_ats_companies.json", "w", encoding="utf-8") as f:
        json.dump(final_valid, f, indent=4)

    with open("all_ats_slugs_verify/failed_ats_companies.json", "w", encoding="utf-8") as f:
        json.dump(final_failed, f, indent=4)

    print("\n🎉 Done.")
    print("📁 verified_ats_companies.json")
    print("📁 failed_ats_companies.json  (now includes a 'reason' per slug: not_found / zero_jobs / http_XXX / network_error / bad_json)")


if __name__ == "__main__":
    asyncio.run(main())