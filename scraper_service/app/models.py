from pydantic import BaseModel
from typing import Optional

class ReviewItem(BaseModel):
    text: str
    source: str          # "reddit" | "hn" | "g2" | "capterra" | "blog"
    url: str
    date: str            # ISO string or relative
    upvotes: int = 0
    platform: str = ""

class ScrapeRequest(BaseModel):
    product_name: str
    job_id: str

class ScrapeResponse(BaseModel):
    job_id: str
    reviews: list[ReviewItem]
    total_count: int