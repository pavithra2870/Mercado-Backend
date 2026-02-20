from pydantic import BaseModel
from typing import Optional

class ReviewInput(BaseModel):
    text: str
    source: str
    url: str
    date: str
    upvotes: int = 0
    platform: str = ""
    # From classifier
    sentiment: str = "neutral"
    sentiment_score: float = 0.5
    quality_score: float = 0.5
    is_genuine: bool = True

class AnalyzeRequest(BaseModel):
    product_name: str
    reviews: list[ReviewInput]
    job_id: str
    mau: Optional[int] = None
    arpu: Optional[float] = None

class ReportRequest(BaseModel):
    job_id: str
    product_name: str
    analysis_result: dict
    reviews: list[ReviewInput]

class PriorityItem(BaseModel):
    quadrant: str         # "IMMEDIATE" | "STRATEGIC" | "UX" | "MONITOR"
    issue: str
    frequency: str        # "High" | "Medium" | "Low"
    severity: str         # "Critical" | "High" | "Moderate" | "Low"
    affected_users_pct: str

class CompetitorBenchmark(BaseModel):
    competitor_name: str
    metrics: list[str]
    our_scores: list[int]
    competitor_scores: list[int]

class AnalysisResult(BaseModel):
    sentiment_score: float
    market_position: str
    revenue_risk_level: str
    priority_matrix: list[PriorityItem]
    churn_events: list[dict]
    timeline: list[dict]
    benchmarking: CompetitorBenchmark
    strategic_recommendations: list[str]
    executive_summary: str
    technical_gaps: list[dict]
    estimated_monthly_price: float