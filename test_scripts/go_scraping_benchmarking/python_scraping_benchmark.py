import asyncio
import time
import re
import httpx

# Simulates your `clean_html` or Pydantic mapping
def heavy_cpu_processing(text: str):
    # A heavy regex or loop that forces the GIL to hold on
    cleaned = text
    for _ in range(50000):
        cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', cleaned)
    return len(cleaned)

async def fetch_and_process(client: httpx.AsyncClient, url: str):
    try:
        # 1. Network I/O
        response = await client.get(url, timeout=10.0)
        # 2. Heavy CPU block (This freezes the single-threaded event loop!)
        _ = heavy_cpu_processing(response.text)
    except Exception as e:
        pass

async def main():
    url = "https://httpbin.org/bytes/1024"  # Returns ~1KB of random characters
    tasks = []
    
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
    async with httpx.AsyncClient(limits=limits) as client:
        start_time = time.time()
        
        # Dispatch 100 concurrent scraping tasks
        for _ in range(10000):
            tasks.append(fetch_and_process(client, url))
        
        await asyncio.gather(*tasks)
        
        end_time = time.time()
        print(f"Python Total Time: {end_time - start_time:.2f} seconds")

if __name__ == "__main__":
    asyncio.run(main())