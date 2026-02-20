import uuid
import os
from fastapi import BackgroundTasks, FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from .db import init_db, get_db, Job
from .models import AnalyzeRequest, JobResponse, StatusResponse, JobStatus
from dotenv import load_dotenv
load_dotenv()

'''
from fastapi import Security, Depends, Request
from fastapi.security import APIKeyHeader
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# 1. Initialize Rate Limiter (Tracks by client IP)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)'''

#from .queue_manager import enqueue_analysis
from .pipeline import run_pipeline
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="Product Research Engine", lifespan=lifespan)
origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "https://market-research-agent-f5ny.onrender.com"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,             # Allows specific origins
    allow_credentials=True,
    allow_methods=["*"],               # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],               # Allows all headers
)

@app.post("/analyze", response_model=JobResponse)
#@limiter.limit("3/hour")  # Limit: 3 requests per hour per user
async def analyze(req: AnalyzeRequest,background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    #request: Request, # SlowAPI requires the 'request' parameter
    #_auth = Depends(verify_api_key) # Locks the route
    job_id = str(uuid.uuid4())
    job = Job(
        job_id=job_id,
        product_name=req.product_name,
        status=JobStatus.QUEUED,
        stage="Queued — waiting for worker",
        mau=req.monthly_active_users,
        arpu=req.avg_revenue_per_user,
    )
    db.add(job)
    await db.commit()

    # Push to RQ
    background_tasks.add_task(
        run_pipeline, 
        job_id, 
        req.product_name, 
        req.monthly_active_users, 
        req.avg_revenue_per_user
    )
    return JobResponse(
        job_id=job_id,
        status=JobStatus.QUEUED,
        message=f"Job queued. Poll /status/{job_id} for updates.",
    )

@app.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).where(Job.job_id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    report_url = f"/report/{job_id}" if job.status == JobStatus.DONE else None
    return StatusResponse(
        job_id=job_id,
        status=job.status,
        stage=job.stage,
        progress_pct=job.progress_pct,
        error=job.error,
        report_url=report_url,
    )

@app.get("/report/{job_id}")
async def get_report(job_id: str, db: AsyncSession = Depends(get_db)):
    analysis_url = os.getenv("ANALYSIS_URL", "http://127.0.0.1:8003").rstrip("/")
    return RedirectResponse(f"{analysis_url}/report/{job_id}")

@app.get("/result/{job_id}")
async def get_result_json(job_id: str, db: AsyncSession = Depends(get_db)):
    """Machine-readable JSON result."""
    result = await db.execute(select(Job).where(Job.job_id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    if not job.result_json:
        raise HTTPException(400, "No result yet")
    return job.result_json

@app.get("/health")
async def health():
    return {"status": "I AM THE NEW ONE"}

@app.post("/cancel/{job_id}", response_model=StatusResponse)
async def cancel_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Stops a job by marking it CANCELLED."""
    result = await db.execute(select(Job).where(Job.job_id == job_id))
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.status in [JobStatus.DONE, JobStatus.FAILED]:
        raise HTTPException(status_code=400, detail="Job already finished")

    # Mark as cancelled
    job.status = JobStatus.CANCELLED # Make sure 'cancelled' is in your Enum!
    job.stage = "Analysis stopped by user."
    job.error = "User cancellation"
    await db.commit()
    
    return StatusResponse(
        job_id=job.job_id,
        status=job.status,
        stage=job.stage,
        progress_pct=job.progress_pct,
        error=job.error
    )