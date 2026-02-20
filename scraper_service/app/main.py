import asyncio
from fastapi import FastAPI
from .models import ScrapeRequest, ScrapeResponse, ReviewItem

# Import Scrapers
from .scrapers.reddit_scraper import scrape_reddit
from .scrapers.hn_scraper import scrape_hn
from .scrapers.bs4_scraper import scrape_web_reviews
from .scrapers.exa_scraper import scrape_with_exa  # <--- NEW IMPORT

from .dedup import deduplicate_and_weight

app = FastAPI(title="Scraper Service")

@app.post("/scrape", response_model=ScrapeResponse)
async def scrape(req: ScrapeRequest):
    query = req.product_name
    print(f"[Scraper] Starting orchestra for: {query}")

    # Run ALL scrapers in parallel
    results = await asyncio.gather(
        scrape_reddit(query, limit=20),
        scrape_hn(query, limit=20),
        scrape_web_reviews(query, limit=10), # Reduced limit since Exa covers web too
        scrape_with_exa(query, limit=20),    # <--- NEW CALL
        return_exceptions=True,
    )

    # Unpack results safely
    reddit_reviews = results[0] if isinstance(results[0], list) else []
    hn_reviews     = results[1] if isinstance(results[1], list) else []
    web_reviews    = results[2] if isinstance(results[2], list) else []
    exa_reviews    = results[3] if isinstance(results[3], list) else []

    # Log errors
    if isinstance(results[0], Exception): print(f"[Scraper] Reddit failed: {results[0]}")
    if isinstance(results[1], Exception): print(f"[Scraper] HN failed: {results[1]}")
    if isinstance(results[2], Exception): print(f"[Scraper] Web failed: {results[2]}")
    if isinstance(results[3], Exception): print(f"[Scraper] Exa failed: {results[3]}")

    # Combine all sources
    all_reviews = reddit_reviews + hn_reviews + web_reviews + exa_reviews

    # 1. Deduplicate by URL (Exact Match)
    seen_urls = set()
    unique_reviews = []
    for r in all_reviews:
        if r.url not in seen_urls:
            seen_urls.add(r.url)
            unique_reviews.append(r)

    print(f"[Scraper] Total raw: {len(all_reviews)} -> Unique URL: {len(unique_reviews)}")

    # 2. Semantic Deduplication & Clustering (The "Smart" Dedup)
    weighted_clusters = deduplicate_and_weight(unique_reviews)

    # 3. Format for Response
    cluster_reviews = [
        ReviewItem(
            text=c["representative_text"],
            source=c["source"],
            url=f"cluster_{c['cluster_id']}", # Virtual URL for the cluster
            date="recent",
            upvotes=c["upvotes"],
            platform=c["source"],
        )
        for c in weighted_clusters
    ]

    return ScrapeResponse(
        job_id=req.job_id,
        reviews=[r.model_dump() for r in cluster_reviews],
        total_count=len(cluster_reviews),
    )

@app.get("/health")
def health():
    return {"status": "ok"}