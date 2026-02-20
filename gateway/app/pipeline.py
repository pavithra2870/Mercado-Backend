"""
pipeline.py — RQ worker task.
Orchestrates scraper → classifier → analysis service calls.
Updates job status in DB at each stage.
"""
import os
import httpx
import asyncio
import sqlalchemy
from sqlalchemy import create_engine, text
from .db import get_db_context, Job, JobStatus # Ensure you have a way to get DB context outside request
from sqlalchemy import select
from datetime import datetime
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = BASE_DIR / "data" / "research.db"

#HF_TOKEN = os.getenv("HF_TOKEN")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
# Sync engine for the RQ worker (RQ runs sync functions)
if "+aiosqlite" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("+aiosqlite", "")

SCRAPER_URL    = os.getenv("SCRAPER_URL",    "http://127.0.0.1:8001") #"http://scraper_service:8001"
CLASSIFIER_URL = os.getenv("CLASSIFIER_URL", "http://127.0.0.1:8002") #"http://classifier_service:8002"
ANALYSIS_URL   = os.getenv("ANALYSIS_URL",   "http://127.0.0.1:8003") #"http://analysis_service:8003"

engine = create_engine(DATABASE_URL)
def check_if_cancelled(job_id: str) -> bool:
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT status FROM jobs WHERE job_id = :job_id"),
            {"job_id": job_id}
        ).fetchone()
        return result is not None and result[0] == JobStatus.CANCELLED
def _update_job(job_id: str, **kwargs):
    kwargs["updated_at"] = datetime.utcnow()

    # 🔥 CRITICAL FIX — serialize dicts for SQLite
    if "result_json" in kwargs and isinstance(kwargs["result_json"], dict):
        kwargs["result_json"] = json.dumps(kwargs["result_json"])

    set_clause = ", ".join(f"{k} = :{k}" for k in kwargs)

    with engine.connect() as conn:
        conn.execute(
            text(f"UPDATE jobs SET {set_clause} WHERE job_id = :job_id"),
            {**kwargs, "job_id": job_id},
        )
        conn.commit()

def run_pipeline(job_id: str, product_name: str, mau: int | None, arpu: float | None):
    """
    Main RQ task. Runs synchronously, calls microservices via httpx.
    Stages:
      1. Scraper Service  → raw reviews
      2. Classifier Service → filtered + scored reviews
      3. Analysis Service → full AnalysisResult
      4. Analysis Service → PDF report
    """
    try:
        if check_if_cancelled(job_id):
            return

        # ── STAGE 1: SCRAPING ────────────────────────────────────────
        _update_job(job_id, status="scraping", stage="Scraping reviews from Reddit, HN, G2...", progress_pct=10)
        
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{SCRAPER_URL}/scrape", json={"product_name": product_name, "job_id": job_id})
            resp.raise_for_status()
            scrape_result = resp.json()
        
        raw_reviews = scrape_result.get("reviews", [])
        if not raw_reviews:
            raise ValueError("Scraper returned 0 reviews. Check product name or sources.")
        
        print(f"[{job_id}] Scraping done: {len(raw_reviews)} raw reviews")
        
        if check_if_cancelled(job_id):
            return

        _update_job(job_id, stage=f"Scraped {len(raw_reviews)} raw items. Classifying...", progress_pct=30)

        if check_if_cancelled(job_id):
            return

        # ── STAGE 2: CLASSIFICATION ──────────────────────────────────
        _update_job(job_id, status="classifying", stage="Filtering spam, classifying quality...", progress_pct=35)

        with httpx.Client(timeout=180.0) as client:
            resp = client.post(f"{CLASSIFIER_URL}/classify", json={"reviews": raw_reviews, "job_id": job_id, "product_name": product_name})
            resp.raise_for_status()
            classify_result = resp.json()

        clean_reviews = classify_result.get("reviews", [])
        if len(clean_reviews) < 5:
            print(f"[{job_id}] Warning: only {len(clean_reviews)} reviews passed filter. Using top raw.")
            clean_reviews = raw_reviews[:15]

        print(f"[{job_id}] Classification done: {len(clean_reviews)} clean reviews")

        if check_if_cancelled(job_id):
            return

        _update_job(job_id, stage=f"{len(clean_reviews)} quality reviews. Running analysis...", progress_pct=55)

        if check_if_cancelled(job_id):
            return


        # ── STAGE 3: ANALYSIS ────────────────────────────────────────
        _update_job(job_id, status="analyzing", stage="Running 4 parallel AI agents...", progress_pct=60)

        with httpx.Client(timeout=300.0) as client:
            resp = client.post(f"{ANALYSIS_URL}/analyze", json={
                "product_name": product_name,
                "reviews": clean_reviews,
                "job_id": job_id,
                "mau": mau,
                "arpu": arpu,
            })
            resp.raise_for_status()
            analysis_result = resp.json()

        print(f"[{job_id}] Analysis done.")

        if check_if_cancelled(job_id):
            return
        _update_job(job_id, stage="Generating PDF report...", progress_pct=80)


        # ── STAGE 4: REPORT GENERATION ───────────────────────────────
        _update_job(job_id, status="generating", stage="Minting PDF...", progress_pct=85)

        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{ANALYSIS_URL}/generate_report", json={
                "job_id": job_id,
                "product_name": product_name,
                "analysis_result": analysis_result,
                "reviews": clean_reviews,
            })
            resp.raise_for_status()
            gen_result = resp.json()

        report_path = gen_result.get("report_path")
        
        _update_job(
            job_id,
            status="done",
            stage="Complete",
            progress_pct=100,
            report_path=report_path,
            result_json=analysis_result,  # stored as JSON text
        )
        print(f"[{job_id}] Pipeline complete. Report: {report_path}")

    except Exception as e:
        import traceback
        err = traceback.format_exc()
        print(f"[{job_id}] PIPELINE FAILED: {err}")
        _update_job(job_id, status="failed", stage="Failed", error=str(e), progress_pct=0)
        raise
