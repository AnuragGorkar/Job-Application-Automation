import asyncio
import json
import httpx

async def verify_endpoint(client, unique_key, config, semaphore):
    tenant = config["tenant"]
    server = config["server"]
    portal_id = config["portal_id"]
    api_url = config["api_url"]
    
    # Crucial: Workday servers frequently return a 403 Forbidden if the 
    # request lacks a Referer matching the expected frontend URL.
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"https://{tenant}.{server}.myworkdayjobs.com/en-US/{portal_id}"
    }
    
    # A lightweight limit: 1 payload to test if the endpoint is alive
    payload = {
        "appliedFacets": {},
        "limit": 1,
        "offset": 0,
        "searchText": ""
    }
    
    async with semaphore:
        for attempt in range(3):
            try:
                response = await client.post(api_url, json=payload, headers=headers, timeout=12.0)
                
                # Handle WAF rate limiting gracefully
                if response.status_code == 429:
                    await asyncio.sleep(2.0 * (2 ** attempt))
                    continue
                    
                if response.status_code != 200:
                    return unique_key, config, "failed", f"HTTP {response.status_code}"
                
                # Check 1: Is it actually JSON, or a WAF HTML block page?
                try:
                    data = response.json()
                except json.JSONDecodeError:
                    return unique_key, config, "failed", "Returned HTML/WAF block"
                
                # Check 2: Does it have the correct schema?
                if "total" not in data or "jobPostings" not in data:
                    return unique_key, config, "failed", "Invalid JSON schema"
                
                # Check 3: Is the job board actually active?
                total_jobs = data.get("total", 0)
                config["total_active_jobs"] = total_jobs
                
                if total_jobs > 0:
                    return unique_key, config, "active", f"{total_jobs} jobs found"
                else:
                    return unique_key, config, "empty", "0 jobs"
                    
            except httpx.RequestError as e:
                # Network timeouts
                await asyncio.sleep(2.0)
                continue
                
        return unique_key, config, "failed", "Connection timed out"

async def run_verification():
    try:
        with open("final_workday_companies_config.json", "r") as f:
            raw_configs = json.load(f)
    except FileNotFoundError:
        print("❌ workday_companies_config.json not found.")
        return

    print(f"🔍 Verifying {len(raw_configs)} configurations...")
    
    # Safe concurrency to avoid triggering global 429s across Workday networks
    semaphore = asyncio.Semaphore(10)
    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    
    active_configs = {}
    empty_configs = {}
    failed_configs = {}
    
    async with httpx.AsyncClient(limits=limits, verify=False) as client:
        tasks = [verify_endpoint(client, key, conf, semaphore) for key, conf in raw_configs.items()]
        
        for future in asyncio.as_completed(tasks):
            unique_key, config, status, message = await future
            
            if status == "active":
                active_configs[unique_key] = config
                print(f"✅ ACTIVE: {config['tenant']} -> {message}")
            elif status == "empty":
                empty_configs[unique_key] = config
                print(f"⚠️ EMPTY: {config['tenant']} -> Board is valid but has 0 jobs")
            else:
                config["fail_reason"] = message
                failed_configs[unique_key] = config
                print(f"❌ FAILED: {config['tenant']} -> {message}")

    # Output the triaged lists
    with open("s2_workday_verified_active.json", "w") as f:
        json.dump(active_configs, f, indent=2)
        
    with open("s2_workday_verified_empty.json", "w") as f:
        json.dump(empty_configs, f, indent=2)
        
    with open("s2_workday_failed_verification.json", "w") as f:
        json.dump(failed_configs, f, indent=2)

    print("\n🎉 Verification Complete!")
    print(f"   🟢 {len(active_configs)} Active and ready to scrape.")
    print(f"   🟡 {len(empty_configs)} Valid but currently empty.")
    print(f"   🔴 {len(failed_configs)} Failed (Dead APIs or WAF blocks).")

if __name__ == "__main__":
    asyncio.run(run_verification())