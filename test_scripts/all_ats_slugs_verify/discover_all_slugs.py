import re
import json
import time
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}
MAX_RETRIES = 4
BASE_BACKOFF = 5  # seconds -- archive.org CDX is slow/flaky on big queries, give it room

ats_configs = {
    "smartrecruiters": {
        "url": "https://web.archive.org/cdx/search/cdx?url=careers.smartrecruiters.com/*&output=text&fl=original&collapse=urlkey",
        "path_regex": r'careers\.smartrecruiters\.com/([^/?#\s]+)',
    },
    "greenhouse": {
        "url": "https://web.archive.org/cdx/search/cdx?url=boards.greenhouse.io/*&output=text&fl=original&collapse=urlkey",
        "path_regex": r'boards\.greenhouse\.io/([^/?#\s]+)',
        # embed widget puts the real token in ?for=SLUG, not the path -> path regex alone misses/mis-captures these
        "param_regex": r'[?&]for=([^&\s]+)',
    },
    "lever": {
        "url": "https://web.archive.org/cdx/search/cdx?url=jobs.lever.co/*&output=text&fl=original&collapse=urlkey",
        "path_regex": r'jobs\.lever\.co/([^/?#\s]+)',
    },
    "ashby": {
        "url": "https://web.archive.org/cdx/search/cdx?url=jobs.ashbyhq.com/*&output=text&fl=original&collapse=urlkey",
        "path_regex": r'jobs\.ashbyhq\.com/([^/?#\s]+)',
    },
}

IGNORE_EXACT = {
    'embed', 'assets', 'static', 'api', 'v1', 'js', 'css',
    'favicon.ico', 'robots.txt', 'sitemap.xml', 'images', 'fonts',
    'feed', 'profile', 'search', 'jobs', 'job', 'careers', 'account',
    'settings', 'login', 'logout', 'app', 'index', 'search-jobs',
    'similar-jobs', 'other-jobs', 'saved-jobs',
}

# UUID-shaped segment (with either - or _ as separator) -> internal ID, not a slug
UUID_SEGMENT = re.compile(r'^[0-9a-fA-F]{8}[_-][0-9a-fA-F]{4}[_-][0-9a-fA-F]{4}[_-][0-9a-fA-F]{4}[_-][0-9a-fA-F]{12}')

# Real slugs are ascii alnum + . _ - only, reasonable length
VALID_SLUG = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')


def clean_slug(raw: str):
    if not raw or '%' in raw:                 # leftover url-encoding artifact -> junk
        return None
    low = raw.lower()
    if low in IGNORE_EXACT:
        return None
    if low.startswith('root.') or low.startswith('root_'):   # Ashby internal id leakage
        return None
    if UUID_SEGMENT.match(raw.replace('-', '_')):
        return None
    if not VALID_SLUG.match(raw):
        return None
    return raw


def fetch_cdx(url: str, ats: str):
    """Fetch a CDX dump with retries + diagnostics. Returns None if it never succeeds."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, timeout=90, headers=HEADERS)
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️  [{ats}] attempt {attempt}/{MAX_RETRIES} network error: {e}")
        else:
            body_len = len(response.text)
            if response.status_code != 200:
                print(f"   ⚠️  [{ats}] attempt {attempt}/{MAX_RETRIES} "
                      f"status={response.status_code} body_len={body_len} "
                      f"preview={response.text[:200]!r}")
            elif body_len == 0:
                print(f"   ⚠️  [{ats}] attempt {attempt}/{MAX_RETRIES} status=200 but empty body")
            else:
                print(f"   ✓  [{ats}] status=200 body_len={body_len}")
                return response.text

        if attempt < MAX_RETRIES:
            wait = BASE_BACKOFF * (2 ** (attempt - 1))
            print(f"   ⏳ [{ats}] retrying in {wait}s...")
            time.sleep(wait)

    return None


all_slugs = {}

for ats, config in ats_configs.items():
    print(f"Fetching data for {ats} (this might take a moment)...")

    text = fetch_cdx(config["url"], ats)

    if text is None:
        print(f"❌ [{ats}] Gave up after {MAX_RETRIES} attempts. Skipping this board.\n")
        continue

    candidates = set(re.findall(config["path_regex"], text))
    if "param_regex" in config:
        candidates |= set(re.findall(config["param_regex"], text))

    if len(candidates) == 0:
        # Dump raw text so you can actually see what archive.org sent back
        dump_path = f"{ats}_raw_cdx_dump.txt"
        with open(dump_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"   ⚠️  [{ats}] 0 regex matches despite a 200 response — "
              f"dumped raw body to {dump_path} for inspection")

    clean = set()
    for c in candidates:
        cleaned = clean_slug(c)
        if cleaned:
            clean.add(cleaned)

    all_slugs[ats] = clean
    print(f"✅ {ats}: {len(candidates)} raw candidates -> {len(clean)} clean slugs "
          f"({len(candidates) - len(clean)} filtered as junk)\n")

serializable_slugs = {key: sorted(value) for key, value in all_slugs.items()}
with open("all_ats_slugs_verify/company_slugs.json", "w") as file:
    json.dump(serializable_slugs, file, indent=4)