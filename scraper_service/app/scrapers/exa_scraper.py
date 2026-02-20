from exa_py import Exa
import os
import asyncio
from dotenv import load_dotenv
from ..models import ReviewItem

load_dotenv()

# --- Configuration for Diversification ---
SOURCE_MAPPING = {
    "reddit.com": "reddit",
    "x.com": "twitter",
    "twitter.com": "twitter",
    "news.ycombinator.com": "hackernews",
    "producthunt.com": "producthunt",
    "g2.com": "b2b_reviews",
    "trustpilot.com": "reviews",
    "capterra.com": "b2b_reviews",
    "stackoverflow.com": "technical",
    "medium.com": "expert_blog",
    "substack.com": "expert_blog",
    "apps.apple.com": "app_store",   # Added for those mobile reviews
    "justuseapp.com": "reviews",    # Added for those review aggregator sites
    "toolstac.com": "expert_blog",  # Added for the tools review site you found
    "stackoverflow.com": "technical"
}

# Define different "perspectives" to search for
RESEARCH_STRATEGIES = [
    {
        "label": "community", 
        "query": "Detailed user reviews and unfiltered complaints about", 
        "num": 5,
        "domains": ["reddit.com", "threads.net", "forum.growthhackers.com"]
    },
    {
        "label": "technical", 
        "query": "Technical limitations, bugs, and developer feedback for", 
        "num": 5,
        "domains": ["news.ycombinator.com", "stackoverflow.com", "github.com"]
    },
    {
        "label": "professional", 
        "query": "B2B software reviews, enterprise pricing complaints, and UX analysis of", 
        "num": 5,
        "domains": ["g2.com", "trustpilot.com", "capterra.com", "producthunt.com"]
    },
    {
        "label": "comparisons", 
        "query": "Comprehensive alternatives and vs comparisons for", 
        "num": 5
    }
]
async def scrape_with_exa(query: str, limit: int = 20) -> list[ReviewItem]:
    print(f"[Exa] Starting diversified neural search for: {query}")
    
    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        print("[Exa] ⚠️ API Key missing!")
        return []

    # Run multiple search strategies in parallel
    tasks = [
        asyncio.to_thread(_run_exa_sync, api_key, f"{strat['query_suffix']} {query}", strat['num'])
        for strat in RESEARCH_STRATEGIES
    ]
    
    results_nested = await asyncio.gather(*tasks)
    
    # Flatten results and remove duplicates by URL
    all_reviews = []
    seen_urls = set()
    for sublist in results_nested:
        for item in sublist:
            if item.url not in seen_urls:
                all_reviews.append(item)
                seen_urls.add(item.url)

    print(f"[Exa] Total unique results found: {len(all_reviews)}")
    return all_reviews[:limit]

def _run_exa_sync(api_key: str, full_query: str, limit: int, domains: list = None) -> list[ReviewItem]:
    try:
        exa = Exa(api_key)
        # We switch to 'auto' or 'deep' for better reasoning
        search_params = {
            "query": full_query,
            "type": "auto", # 'auto' intelligently balances neural + keyword
            "num_results": limit,
            "text": {"max_characters": 1500}, # Increased for better LLM context later
            "highlights": {"num_sentences": 5, "highlights_per_url": 1},
            "livecrawl": "always" # Ensures you aren't getting 2-year-old cached data
        }
        
        if domains:
            search_params["include_domains"] = domains

        response = exa.search_and_contents(**search_params)

        reviews = []
        for result in response.results:
            domain = result.url.lower()
            platform = "web"
            for key, val in SOURCE_MAPPING.items():
                if key in domain:
                    platform = val
                    break

            # If it's a deep review, we want more than just a snippet
            content = result.highlights[0] if result.highlights else (result.text[:1200] if result.text else "")
            
            if len(content) < 60: continue

            reviews.append(ReviewItem(
                text=f"Title: {result.title}\nContent: {content}",
                source=f"exa_{platform}",
                url=result.url,
                date=result.published_date or "2026-recent", # Grounding it in current year
                upvotes=0,
                platform=platform
            ))
        return reviews
    except Exception as e:
        print(f"[Exa] Error on query '{full_query[:30]}...': {e}")
        return []