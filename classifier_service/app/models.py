from pydantic import BaseModel
from typing import Optional


class RawReview(BaseModel):
    text: str
    source: str
    url: str
    date: str
    upvotes: int = 0
    platform: str = ""


class ClassifiedReview(RawReview):
    is_genuine: bool
    quality_score: float          # 0.0 – 1.0
    sentiment: str                # "positive" | "negative" | "neutral"
    sentiment_score: float        # confidence 0.0 – 1.0
    spam_reason: Optional[str] = None


class ClassifyRequest(BaseModel):
    reviews: list[RawReview]
    product_name: str
    job_id: str


class SentimentSummary(BaseModel):
    overall_label: str            # "positive" | "neutral" | "negative"
    weighted_score: float         # 0.0 – 10.0
    positive_pct: float
    neutral_pct: float
    negative_pct: float
    total: int


class ClassifyResponse(BaseModel):
    job_id: str
    reviews: list[ClassifiedReview]
    rejected_count: int
    sentiment_summary: SentimentSummary   # aggregate across all clean reviews