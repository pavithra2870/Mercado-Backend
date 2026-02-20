import asyncio
import random
from datetime import datetime, timezone
from urllib.parse import quote_plus
from ..models import ReviewItem
from curl_cffi.requests import AsyncSession, RequestsError

# We remove the static User-Agent because curl_cffi's "impersonate" 
# will automatically generate the perfect, matching User-Agent and headers.
# We only add headers that make it look like organic browsing.
EXTRA_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}

SUBREDDITS_TO_SEARCH = [
    "programming", "webdev", "MachineLearning", "devops",
    "SoftwareEngineering", "cscareerquestions", "technology",
    "artificial", "ArtificialIntelligence", "learnprogramming", "ProductManagement", 
    "Entrepreneur", "SideProject", "MarketResearch", "Startups", "SaaS", "GrowthHacking", 
    "AskReddit", "ConsumerBehavior", "BuyItForLife", "gadgets"
]

async def _human_sleep(min_sec: float = 2.0, max_sec: float = 4.5):
    """Simulates a human reading/scrolling delay."""
    await asyncio.sleep(random.uniform(min_sec, max_sec))

async def scrape_reddit(query: str, limit: int = 30) -> list[ReviewItem]:
    """Stealth search Reddit via old.reddit.com JSON using Chrome TLS impersonation."""
    reviews = []
    search_terms = [
        f"{query} review",
        f"{query} problems",
        f"{query} alternatives",
    ]

    # impersonate="chrome" perfectly mimics a real Chrome browser's network fingerprint
    async with AsyncSession(impersonate="chrome", headers=EXTRA_HEADERS, timeout=30.0) as client:
        for term in search_terms:
            try:
                encoded_term = quote_plus(term)
                url = f"https://www.reddit.com/search.json?q={encoded_term}&sort=relevance&t=year&limit=10"
                
                # Fetch with retry logic for 429s
                resp = await _fetch_with_retry(client, url)
                if not resp or resp.status_code != 200:
                    continue
                
                data = resp.json()
                posts = data.get("data", {}).get("children", [])
                
                for post in posts:
                    p = post.get("data", {})
                    title = p.get("title", "")
                    selftext = p.get("selftext", "")
                    combined = f"Title: {title}\nReview: {selftext}"
                    
                    if len(combined.strip()) < 30:
                        continue
                    
                    ts = p.get("created_utc", 0)
                    date_str = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else "unknown"
                    
                    reviews.append(ReviewItem(
                        text=combined,
                        source="reddit",
                        url=f"https://reddit.com{p.get('permalink', '')}",
                        date=date_str,
                        upvotes=p.get("score", 0),
                        platform="reddit",
                    ))
                
                await _human_sleep() # Jittered sleep to avoid pattern detection
                
            except Exception as e:
                print(f"[Reddit] Error for '{term}': {e}")
                continue
    
        # Scrape comments using the SAME secure session
        comment_reviews = await _scrape_top_post_comments(client, query)
        reviews.extend(comment_reviews)
    
    # Deduplicate by URL
    seen = set()
    unique = []
    for r in reviews:
        if r.url not in seen:
            seen.add(r.url)
            unique.append(r)
    
    return unique[:limit]


async def _scrape_top_post_comments(client: AsyncSession, query: str) -> list[ReviewItem]:
    """Get comments from the most relevant Reddit post using the established session."""
    reviews = []
    try:
        encoded = quote_plus(query)
        url = f"https://www.reddit.com/search.json?q={encoded}&sort=top&t=year&limit=3"
        
        resp = await _fetch_with_retry(client, url)
        if not resp or resp.status_code != 200:
            return []
        
        posts = resp.json().get("data", {}).get("children", [])
        for post in posts[:2]:
            permalink = post["data"].get("permalink", "")
            if not permalink:
                continue
            
            comment_url = f"https://www.reddit.com{permalink}.json?limit=20"
            await _human_sleep(1.5, 3.0)
            
            cresp = await _fetch_with_retry(client, comment_url)
            if not cresp or cresp.status_code != 200:
                continue
            
            comment_data = cresp.json()
            if len(comment_data) < 2:
                continue
            
            comments = comment_data[1].get("data", {}).get("children", [])
            for c in comments:
                body = c.get("data", {}).get("body", "")
                if len(body) > 50:
                    ts = c["data"].get("created_utc", 0)
                    date_str = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else "unknown"
                    reviews.append(ReviewItem(
                        text=body[:1000],
                        source="reddit_comment",
                        url=f"https://reddit.com{permalink}",
                        date=date_str,
                        upvotes=c["data"].get("score", 0),
                        platform="reddit",
                    ))
    except Exception as e:
        print(f"[Reddit Comments] Error: {e}")
    
    return reviews


async def _fetch_with_retry(client: AsyncSession, url: str, max_retries: int = 2):
    """Handles Reddit's occasional '429 Too Many Requests' gracefully."""
    for attempt in range(max_retries):
        try:
            resp = await client.get(url)
            if resp.status_code == 429:
                # If Reddit catches us, back off exponentially
                wait_time = (attempt + 1) * random.uniform(4.0, 7.0)
                print(f"[Reddit] 429 Rate Limit hit. Backing off for {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)
                continue
            return resp
        except RequestsError as e:
            print(f"[Reddit] Network error: {e}")
            await asyncio.sleep(2.0)
    return None