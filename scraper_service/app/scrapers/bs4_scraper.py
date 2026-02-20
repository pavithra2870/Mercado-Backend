import asyncio
import random
from datetime import datetime
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession, RequestsError
from ..models import ReviewItem

# We drop the hardcoded User-Agent. curl_cffi will generate the exact 
# User-Agent that matches the cryptographic TLS fingerprint of Chrome.
EXTRA_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

async def _human_sleep(min_sec: float = 1.5, max_sec: float = 3.5):
    """Simulates human reading/scrolling delay."""
    await asyncio.sleep(random.uniform(min_sec, max_sec))

async def _fetch_with_retry(client: AsyncSession, url: str, max_retries: int = 2):
    """Gracefully handles Cloudflare 403s and 429 Rate Limits."""
    for attempt in range(max_retries):
        try:
            # Set a fake referer for each request to look organic
            client.headers.update({"Referer": "https://www.google.com/"})
            resp = await client.get(url)
            
            if resp.status_code in [403, 429]:
                wait_time = (attempt + 1) * random.uniform(3.0, 6.0)
                print(f"[Web Scraper] Blocked ({resp.status_code}) on {url}. Backing off {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)
                continue
            return resp
        except RequestsError as e:
            print(f"[Web Scraper] Network error on {url}: {e}")
            await asyncio.sleep(2.0)
    return None

async def scrape_web_reviews(query: str, limit: int = 15) -> list[ReviewItem]:
    """Finds review pages and scrapes them using Chrome TLS impersonation."""
    reviews = []
    
    # We share a single stealth session across all strategies to simulate one user's browser
    async with AsyncSession(impersonate="chrome", headers=EXTRA_HEADERS, timeout=25.0, allow_redirects=True) as client:
        # Strategy 1: Direct G2 search
        g2_reviews = await _scrape_g2(client, query)
        reviews.extend(g2_reviews)
        
        # Strategy 2: ProductHunt discussion
        ph_reviews = await _scrape_producthunt(client, query)
        reviews.extend(ph_reviews)
        
        # Strategy 3: General blog search via DuckDuckGo HTML
        blog_reviews = await _scrape_duckduckgo_blogs(client, query)
        reviews.extend(blog_reviews)
    
    return reviews[:limit]

async def _scrape_g2(client: AsyncSession, query: str) -> list[ReviewItem]:
    reviews = []
    slug = query.lower().replace(" ", "-")
    encoded_query = quote_plus(query)
    
    urls_to_try = [
        f"https://www.g2.com/products/{slug}/reviews",
        f"https://www.g2.com/search?query={encoded_query}",
    ]
    
    for url in urls_to_try:
        try:
            resp = await _fetch_with_retry(client, url)
            if not resp or resp.status_code != 200:
                continue
            
            soup = BeautifulSoup(resp.content, "html.parser")
            
            review_els = soup.select("[data-testid='review-content']") or \
                         soup.select(".review-text") or \
                         soup.select(".itemprop-reviewBody") or \
                         soup.select("p.formatted-text")
            
            for el in review_els[:8]:
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 50:
                    reviews.append(ReviewItem(
                        text=text,
                        source="g2",
                        url=url,
                        date="recent",
                        upvotes=0,
                        platform="g2",
                    ))
            
            await _human_sleep()
            if reviews:
                break
                
        except Exception as e:
            print(f"[G2] Error: {e}")
            continue
    return reviews

async def _scrape_producthunt(client: AsyncSession, query: str) -> list[ReviewItem]:
    reviews = []
    slug = query.lower().replace(" ", "-")
    encoded_query = quote_plus(query)
    
    urls = [
        f"https://www.producthunt.com/products/{slug}/reviews",
        f"https://www.producthunt.com/search?q={encoded_query}",
    ]
    
    for url in urls:
        try:
            resp = await _fetch_with_retry(client, url)
            if not resp or resp.status_code != 200:
                continue
            
            soup = BeautifulSoup(resp.content, "html.parser")
            
            review_els = soup.select("[data-test='review-body']") or \
                         soup.select(".review-text") or \
                         soup.select("div[class*='review']")
            
            for el in review_els[:8]:
                text = el.get_text(separator=" ", strip=True)
                if len(text) > 50:
                    reviews.append(ReviewItem(
                        text=text,
                        source="producthunt",
                        url=url,
                        date="recent",
                        upvotes=0,
                        platform="producthunt",
                    ))
            
            await _human_sleep()
            if reviews:
                break
                
        except Exception as e:
            print(f"[PH] Error: {e}")
    return reviews

async def _scrape_duckduckgo_blogs(client: AsyncSession, query: str) -> list[ReviewItem]:
    reviews = []
    current_year = datetime.now().year # Dynamically grab 2026
    search_query = f"{query} review {current_year}"
    encoded = quote_plus(search_query)
    ddg_url = f"https://html.duckduckgo.com/html/?q={encoded}"
    
    try:
        resp = await _fetch_with_retry(client, ddg_url)
        if not resp or resp.status_code != 200:
            return []
        
        soup = BeautifulSoup(resp.content, "html.parser")
        result_links = soup.select(".result__url")[:5]
        
        result_urls = [link.get("href") or link.get_text(strip=True) for link in result_links]
        result_urls = [u for u in result_urls if u and u.startswith("http")]
        
        for url in result_urls[:3]:
            await _human_sleep()
            try:
                page_resp = await _fetch_with_retry(client, url)
                if not page_resp or page_resp.status_code != 200:
                    continue
                
                page_soup = BeautifulSoup(page_resp.content, "html.parser")
                
                for tag in page_soup(["nav", "footer", "script", "style", "aside"]):
                    tag.decompose()
                
                main = page_soup.select_one("article") or \
                       page_soup.select_one("main") or \
                       page_soup.select_one(".content") or \
                       page_soup.select_one(".post-content")
                
                if main:
                    text = main.get_text(separator=" ", strip=True)
                    if len(text) > 200:
                        reviews.append(ReviewItem(
                            text=text,
                            source="blog",
                            url=url,
                            date="recent",
                            upvotes=0,
                            platform="web",
                        ))
            except Exception as e:
                print(f"[Blog] Error scraping {url}: {e}")
                continue
                
    except Exception as e:
        print(f"[DDG] Error: {e}")
    
    return reviews