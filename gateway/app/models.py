from pydantic import BaseModel
from typing import Optional
from enum import Enum

class JobStatus(str, Enum):
    QUEUED = "queued"
    SCRAPING = "scraping"
    CLASSIFYING = "classifying"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
class AnalyzeRequest(BaseModel):
    product_name: str
    # Optional financial context — improves risk numbers
    monthly_active_users: Optional[int] = None
    avg_revenue_per_user: Optional[float] = None

class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str

class StatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    stage: str
    progress_pct: int
    error: Optional[str] = None
    report_url: Optional[str] = None