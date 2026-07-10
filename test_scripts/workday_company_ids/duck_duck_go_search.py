import httpx
import json
import asyncio
import re
from urllib.parse import urlparse
from ddgs import DDGS
# ==========================================
# PHASE 1: COMMON CRAWL DOMAIN HARVESTER
# ==========================================
async def fetch_with_backoff(client, url, params, max_retries=5):
    base_delay = 5.0
    for attempt in range(max_retries):
        try:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                return resp
            elif resp.status_code in [503, 502, 504, 429]:
                delay = base_delay * (2 ** attempt)
                await asyncio.sleep(delay)
                continue
            return None
        except (httpx.RequestError, httpx.ReadError):
            delay = base_delay * (2 ** attempt)
            await asyncio.sleep(delay)
    return None

async def harvest_workday_domains():
    indexes = [
        "CC-MAIN-2024-18", "CC-MAIN-2024-10", 
        "CC-MAIN-2023-50", "CC-MAIN-2023-40", 
        "CC-MAIN-2023-23"
    ]
    unique_urls = set()
    limits = httpx.Limits(max_connections=1, max_keepalive_connections=1)
    timeout = httpx.Timeout(60.0, connect=15.0)

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        for index_id in indexes:
            index_url = f"https://index.commoncrawl.org/{index_id}-index"
            base_params = {"url": "myworkdayjobs.com", "matchType": "domain", "output": "json"}
            
            print(f"\n📡 [PHASE 1] Querying Index: {index_id} for total pages...")
            resp = await fetch_with_backoff(client, index_url, {**base_params, "showNumPages": "true", "fl": "url"})
            
            if not resp:
                print(f"❌ Failed to get pagination for {index_id}.")
                continue
                
            num_pages = resp.json().get("pages", 1)
            print(f"📊 Found {num_pages} pages in {index_id}.")
            
            for page in range(num_pages):
                print(f"  📥 Fetching page {page + 1}/{num_pages}...")
                page_resp = await fetch_with_backoff(client, index_url, {**base_params, "page": page, "fl": "url"})
                if not page_resp:
                    continue
                
                for line in page_resp.text.splitlines():
                    if not line.strip(): continue
                    try:
                        record = json.loads(line)
                        domain = urlparse(record.get("url", "").strip().lower()).netloc
                        if domain.endswith("myworkdayjobs.com"):
                            unique_urls.add(f"https://{domain}")
                    except json.JSONDecodeError:
                        continue
                await asyncio.sleep(1.0)
            await asyncio.sleep(3.0)

    master_list = sorted(list(unique_urls))
    with open("raw_workday_domains.json", "w") as f:
        json.dump(master_list, f, indent=2)
    print(f"\n🎉 [PHASE 1 COMPLETE] Saved {len(master_list)} raw domains.")


# ==========================================
# PHASE 2: DETERMINISTIC RESOLVER
# ==========================================
async def verify_api_endpoint(client, tenant, server, portal_id):
    api_url = f"https://{tenant}.{server}.myworkdayjobs.com/wday/cxs/{tenant}/{portal_id}/jobs"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json", "Content-Type": "application/json"
    }
    payload = {"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""}
    
    for attempt in range(3):
        try:
            resp = await client.post(api_url, json=payload, headers=headers, timeout=10.0)
            if resp.status_code == 200: return api_url
            elif resp.status_code == 429:
                await asyncio.sleep(2.0 * (2 ** attempt))
                continue
            else: return None
        except (httpx.TimeoutException, httpx.NetworkError):
            await asyncio.sleep(2.0)
            continue
    return None

async def resolve_tenant(client, domain, semaphore):
    match = re.search(r"https://([^.]+)\.(wd\d+)\.myworkdayjobs", domain)
    if not match: return None, domain
    
    tenant, server = match.group(1), match.group(2)
    discovered_portals = set()
    verified_configs = []

    async with semaphore:
        # STAGE A: Redirect
        try:
            redir_resp = await client.get(domain + "/", follow_redirects=True, timeout=12.0)
            parsed = urlparse(str(redir_resp.url))
            parts = [p for p in parsed.path.split("/") if p]
            if parts and parts[-1].lower() not in ['en-us', 'jobs', tenant]: 
                portal_id = parts[-1]
                api_url = await verify_api_endpoint(client, tenant, server, portal_id)
                if api_url:
                    discovered_portals.add(portal_id)
                    verified_configs.append({"company_name": tenant, "api_url": api_url, "portal_id": portal_id, "server": server, "tenant": tenant, "discovery": "redirect"})
        except Exception:
            pass 

        # STAGE B: Sitemap
        for sm_path in ["/siteMap.xml", "/sitemap.xml"]:
            try:
                sm_resp = await client.get(domain + sm_path, timeout=10.0)
                if sm_resp.status_code == 200:
                    found_portals = re.findall(r"https://[^.]+\.wd\d+\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/<]+)/job/", sm_resp.text)
                    for portal_id in set(found_portals):
                        if portal_id not in discovered_portals:
                            api_url = await verify_api_endpoint(client, tenant, server, portal_id)
                            if api_url:
                                discovered_portals.add(portal_id)
                                verified_configs.append({"company_name": tenant, "api_url": api_url, "portal_id": portal_id, "server": server, "tenant": tenant, "discovery": "sitemap"})
                    break 
            except Exception:
                continue

        # STAGE C: Guess Fallback
        if not verified_configs:
            guess_list = ["External", "Careers", "External_Career_Site", "CorporateCareers", "Public", "Global"]
            for portal_id in guess_list:
                api_url = await verify_api_endpoint(client, tenant, server, portal_id)
                if api_url:
                    verified_configs.append({"company_name": tenant, "api_url": api_url, "portal_id": portal_id, "server": server, "tenant": tenant, "discovery": "guess"})
                    break 

        return verified_configs, domain

async def orchestrate_resolution():
    try:
        with open("raw_workday_domains.json", "r") as f:
            raw_domains = json.load(f)
    except FileNotFoundError:
        print("❌ raw_workday_domains.json not found. Run Phase 1 first.")
        return

    print(f"\n🔍 [PHASE 2] Multi-Stage Resolution starting for {len(raw_domains)} domains...")
    semaphore = asyncio.Semaphore(15) 
    limits = httpx.Limits(max_connections=30, max_keepalive_connections=15)
    
    verified_map = {}
    unresolved_domains = []
    
    async with httpx.AsyncClient(limits=limits, verify=False) as client:
        tasks = [resolve_tenant(client, domain, semaphore) for domain in raw_domains]
        for future in asyncio.as_completed(tasks):
            configs, domain = await future
            if configs:
                for conf in configs:
                    unique_key = f"{conf['tenant']}_{conf['portal_id']}"
                    verified_map[unique_key] = conf
                    print(f"✅ MATCH [{conf['discovery']}]: {conf['tenant']} -> {conf['portal_id']}")
            else:
                unresolved_domains.append(domain)

    with open("workday_companies_config.json", "w") as f:
        json.dump(verified_map, f, indent=2)
    with open("workday_unresolved_domains.json", "w") as f:
        json.dump(unresolved_domains, f, indent=2)
        
    print(f"\n🎉 [PHASE 2 COMPLETE]")
    print(f"   ✅ Saved {len(verified_map)} configs to workday_companies_config.json")
    print(f"   💀 Saved {len(unresolved_domains)} failed domains to workday_unresolved_domains.json")


# ==========================================
# PHASE 3: DUCK DUCK GO RESCUE
# ==========================================

# NEW: Synchronous wrapper for the new DDGS library structure
def sync_ddg_search(query):
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=5))
    except Exception:
        return []

async def rescue_domain_via_ddg(client, domain, semaphore):
    match = re.search(r"https://([^.]+)\.(wd\d+)\.myworkdayjobs", domain)
    if not match: return None, domain
    
    tenant, server = match.group(1), match.group(2)
    query = f"site:{tenant}.{server}.myworkdayjobs.com"
    
    async with semaphore:
        try:
            # Run the synchronous DDG search inside an async thread pool wrapper
            results = await asyncio.to_thread(sync_ddg_search, query)
            
            if not results: return None, domain
                
            for result in results:
                url = result.get("href", "")
                portal_match = re.search(r"myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/]+)", url)
                if portal_match:
                    portal_id = portal_match.group(1)
                    api_url = await verify_api_endpoint(client, tenant, server, portal_id)
                    if api_url:
                        return {
                            "company_name": tenant,
                            "api_url": api_url,
                            "portal_id": portal_id,
                            "server": server,
                            "tenant": tenant,
                            "discovery": "duckduckgo"
                        }, domain
        except Exception:
            await asyncio.sleep(3.0)
            
    return None, domain

async def run_ddg_rescue():
    try:
        with open("workday_unresolved_domains.json", "r") as f:
            unresolved_domains = json.load(f)
    except FileNotFoundError:
        print("❌ workday_unresolved_domains.json not found. Run Phase 2 first.")
        return

    print(f"\n🦆 [PHASE 3] Initiating DDG OSINT Rescue for {len(unresolved_domains)} domains...")
    semaphore = asyncio.Semaphore(3)
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
    
    rescued_configs = []
    still_dead = []
    
    async with httpx.AsyncClient(limits=limits) as client:
        chunk_size = 20
        for i in range(0, len(unresolved_domains), chunk_size):
            chunk = unresolved_domains[i:i + chunk_size]
            print(f"Processing chunk {i+1} to {min(i+chunk_size, len(unresolved_domains))}...")
            
            tasks = [rescue_domain_via_ddg(client, domain, semaphore) for domain in chunk]
            for future in asyncio.as_completed(tasks):
                res, domain = await future
                if res:
                    rescued_configs.append(res)
                    print(f"  🦆 RESCUED! {res['tenant']} -> Custom Portal: {res['portal_id']}")
                else:
                    still_dead.append(domain)
                    
            await asyncio.sleep(2.0)

    # Merge rescues with existing configs
    try:
        with open("workday_companies_config.json", "r") as f:
            existing_map = json.load(f)
    except FileNotFoundError:
        existing_map = {}

    for conf in rescued_configs:
        unique_key = f"{conf['tenant']}_{conf['portal_id']}"
        existing_map[unique_key] = conf

    with open("workday_companies_config.json", "w") as f:
        json.dump(existing_map, f, indent=2)
        
    with open("workday_permanently_dead.json", "w") as f:
        json.dump(still_dead, f, indent=2)
        
    print(f"\n🎉 [PIPELINE COMPLETE]")
    print(f"   🦆 Rescued {len(rescued_configs)} custom enterprise portals!")
    print(f"   💀 {len(still_dead)} domains are permanently dead/unresolvable.")
    print(f"   💾 Master config file updated. Total verified portals: {len(existing_map)}")


# ==========================================
# MAIN EXECUTION ROUTINE
# ==========================================
async def main():
    # TIP: Since you already have 'raw_workday_domains.json' and ran Phase 2 earlier, 
    # you can comment out the first two phases below if you strictly want to test Phase 3 right now.
    
    # await harvest_workday_domains()     # Phase 1
    # await orchestrate_resolution()      # Phase 2
    await run_ddg_rescue()                # Phase 3

if __name__ == "__main__":
    asyncio.run(main())
    # print("⚠️  Note: The main execution is commented out to prevent accidental runs. Uncomment to execute the full pipeline.")