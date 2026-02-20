import asyncio
import random
from urllib.parse import quote_plus
from ..models import ReviewItem
from curl_cffi.requests import AsyncSession, RequestsError

HN_API = "https://hn.algolia.com/api/v1"

# Basic headers to look like a standard browser request rather than a script
EXTRA_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://news.ycombinator.com/",
}

async def _human_sleep(min_sec: float = 1.0, max_sec: float = 2.5):
    """Simulates a slight delay between requests."""
    await asyncio.sleep(random.uniform(min_sec, max_sec))

async def _fetch_with_retry(client: AsyncSession, url: str, max_retries: int = 3):
    """Handles Algolia's rate limits (429) with exponential backoff."""
    for attempt in range(max_retries):
        try:
            resp = await client.get(url)
            if resp.status_code == 429:
                wait_time = (attempt + 1) * random.uniform(2.0, 4.0)
                print(f"[HN] 429 Rate Limit hit. Backing off for {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)
                continue
            return resp
        except RequestsError as e:
            print(f"[HN] Network error: {e}")
            await asyncio.sleep(1.5)
    return None

async def scrape_hn(query: str, limit: int = 20) -> list[ReviewItem]:
    """Scrape HN via Algolia using Chrome TLS impersonation and safe encoding."""
    reviews = []
    
    # URL-encode the query so spaces and special characters don't break the API call
    encoded_query = quote_plus(query)
    encoded_review_query = quote_plus(f"{query} review")
    
    endpoints = [
        f"{HN_API}/search?query={encoded_query}&tags=story&hitsPerPage={limit}",
        f"{HN_API}/search?query={encoded_query}&tags=comment&hitsPerPage={limit}",
        f"{HN_API}/search?query={encoded_review_query}&tags=story&hitsPerPage=10",
    ]
    
    # Use curl_cffi to perfectly mimic Chrome's network signature
    async with AsyncSession(impersonate="chrome", headers=EXTRA_HEADERS, timeout=20.0) as client:
        for i, url in enumerate(endpoints):
            try:
                resp = await _fetch_with_retry(client, url)
                if not resp or resp.status_code != 200:
                    continue
                
                hits = resp.json().get("hits", [])
                
                for hit in hits:
                    # Stories have title+story_text, comments have comment_text
                    text = hit.get("comment_text") or hit.get("story_text") or ""
                    title = hit.get("title", "")
                    combined = f"{title}\n{text}".strip()
                    
                    # Ignore overly short or empty comments
                    if len(combined) < 30:
                        continue
                    
                    reviews.append(ReviewItem(
                        text=combined,
                        source="hacker_news",
                        url=f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}",
                        date=hit.get("created_at", "unknown"),
                        upvotes=hit.get("points", 0) or hit.get("num_comments", 0),
                        platform="hn",
                    ))
                
                # Add a small human delay between endpoint calls, except after the last one
                if i < len(endpoints) - 1:
                    await _human_sleep()
                    
            except Exception as e:
                print(f"[HN] Error processing endpoint: {e}")
                continue
    
    # Deduplicate by URL
    seen = set()
    unique = []
    for r in reviews:
        if r.url not in seen:
            seen.add(r.url)
            unique.append(r)
    
    return unique