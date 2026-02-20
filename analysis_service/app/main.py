import asyncio
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from .models import AnalyzeRequest, ReportRequest
from .agents.sentiment_agent import run_sentiment_agent
from .agents.priority_agent import run_priority_agent
from .agents.competitor_agent import run_competitor_agent
from .agents.risk_agent import run_risk_agent
from .report_writer import write_report
from .finance_engine import generate_visualizations
from .report_generator import convert_to_pdf

app = FastAPI(title="Analysis Service")
BASE_DIR = Path(__file__).resolve().parent

# Define the reports directory inside analysis_service/app/
REPORTS_DIR = BASE_DIR / "reports"

# Ensure the directory exists on startup
os.makedirs(REPORTS_DIR, exist_ok=True)

@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    print(f"[Analysis] Starting for: {req.product_name} ({len(req.reviews)} reviews)")
    
    reviews_dicts = [r.model_dump() for r in req.reviews]
    
    # Run all 4 agents in parallel
    results = await asyncio.gather(
        run_sentiment_agent(reviews_dicts),
        run_priority_agent(reviews_dicts, req.product_name),
        run_competitor_agent(reviews_dicts, req.product_name),
        run_risk_agent(reviews_dicts, req.product_name, req.mau, req.arpu),
        return_exceptions=True,
    )
    
    sentiment_result  = results[0] if not isinstance(results[0], Exception) else {}
    priority_result   = results[1] if not isinstance(results[1], Exception) else {}
    competitor_result = results[2] if not isinstance(results[2], Exception) else {}
    risk_result       = results[3] if not isinstance(results[3], Exception) else {}
    
    # Log any agent failures
    for i, (name, r) in enumerate(zip(
        ["Sentiment", "Priority", "Competitor", "Risk"], results
    )):
        if isinstance(r, Exception):
            print(f"[Analysis] {name}Agent failed: {r}")
    
    analysis_result = {
        "sentiment": sentiment_result,
        "priority_matrix": priority_result.get("priority_matrix", []),
        "technical_gaps": priority_result.get("technical_gaps", []),
        "competitor": competitor_result,
        "risk": risk_result,
    }
    
    print(f"[Analysis] All agents complete.")
    return analysis_result


@app.post("/generate_report")
async def generate_report(req: ReportRequest):
    reviews_dicts = [r.model_dump() for r in req.reviews]

    markdown_text = await write_report(
        req.product_name,
        req.analysis_result,
        reviews_dicts,
    )

    chart_paths = generate_visualizations(
        req.analysis_result,
        req.job_id,
        REPORTS_DIR,
    )

    report_path = str(REPORTS_DIR / f"report_{req.job_id}.pdf")

    success = convert_to_pdf(
        markdown_text  = markdown_text,
        output_path    = report_path,
        reviews        = reviews_dicts,
        chart_paths    = chart_paths,
        product_name   = req.product_name,       # ← new
        analysis_result = req.analysis_result,   # ← new (for WCS metadata on cover)
    )

    if not success:
        return {"success": False, "report_path": None, "error": "PDF generation failed"}

    return {"success": True, "report_path": str(report_path)}

@app.get("/health")
def health():
    return {"status": "ok"}
@app.get("/report/{job_id}")
def download_report(job_id: str):
    path = REPORTS_DIR / f"report_{job_id}.pdf"
    if not path.exists():
        raise HTTPException(404, "Report not found")
    return FileResponse(path, media_type="application/pdf")