"""
RiskAgent — financial risk calculation.
Uses real cluster weights + optional MAU/ARPU inputs for calibrated numbers.
"""
import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()


genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
_model = genai.GenerativeModel(
    "gemini-2.5-flash",
    generation_config={"response_mime_type": "application/json"}
)

CHURN_KEYWORDS = [
    "cancel", "cancelled", "canceling", "switching", "switched", "refund",
    "leaving", "left", "unsubscribed", "moved to", "migrated to",
    "going to use", "replacing", "dropped", "quit"
]

def _detect_churn_signals(reviews: list[dict]) -> list[dict]:
    """Identify reviews with explicit churn language."""
    churn_events = []
    for r in reviews:
        text = r.get("text", "").lower()
        matched = [kw for kw in CHURN_KEYWORDS if kw in text]
        if matched:
            churn_events.append({
                "text_snippet": r.get("text", ""),
                "churn_keywords": matched,
                "sentiment": r.get("sentiment", "negative"),
                "quality_score": r.get("quality_score", 0.5),
                "upvotes": r.get("upvotes", 0),
            })
    return churn_events


async def run_risk_agent(
    reviews: list[dict],
    product_name: str,
    mau: int | None = None,
    arpu: float | None = None,
) -> dict:
    churn_events = _detect_churn_signals(reviews)
    
    # Financial math (deterministic, no LLM)
    churn_count = len(churn_events)
    total = len(reviews)
    churn_rate_pct = (churn_count / total * 100) if total > 0 else 0
    
    financial_impact = {}
    if mau and arpu:
        # Calibrated: at_risk_users = churn_rate × MAU × quality_weight
        avg_quality = sum(e["quality_score"] for e in churn_events) / max(len(churn_events), 1)
        at_risk_users = int(mau * (churn_rate_pct / 100) * avg_quality)
        monthly_revenue_at_risk = at_risk_users * arpu
        financial_impact = {
            "at_risk_users": at_risk_users,
            "monthly_revenue_at_risk": round(monthly_revenue_at_risk, 2),
            "annual_revenue_at_risk": round(monthly_revenue_at_risk * 12, 2),
            "calibrated": True,
        }
    else:
        # Qualitative only
        financial_impact = {
            "calibrated": False,
            "note": "Provide MAU + ARPU in request for calibrated numbers",
        }
    
    # LLM for qualitative analysis only
    churn_context = "\n".join([
        f"- {e['text_snippet']} (keywords: {', '.join(e['churn_keywords'])})"
        for e in churn_events[:20]
    ])
    
    prompt = f"""
    Analyze churn risk for '{product_name}' based on these explicit churn signals:

    {churn_context if churn_context else "No explicit churn signals detected."}
    
    Churn signal rate: {churn_rate_pct:.1f}% of analyzed reviews
    
    Return JSON only:
    {{
      "churn_events": [
        {{"category": "Auth|Performance|Price|UX|Feature", "severity_score": 1-10, "description": "brief"}}
      ],
      "timeline": [
        {{"period": "Week 1", "incident_count": 5, "sentiment": "Negative|Critical|Neutral"}}
      ],
      "estimated_monthly_price": 50.0,
      "risk_summary": "2-sentence risk assessment"
    }}
    """
    
    try:
        resp = await _model.generate_content_async(prompt)
        result = json.loads(resp.text)
        result["financial_impact"] = financial_impact
        result["churn_signal_count"] = churn_count
        result["churn_rate_pct"] = round(churn_rate_pct, 1)
        return result
    except Exception as e:
        print(f"[RiskAgent] Error: {e}")
        return {
            "churn_events": [],
            "timeline": [],
            "estimated_monthly_price": 50.0,
            "financial_impact": financial_impact,
            "churn_signal_count": churn_count,
            "churn_rate_pct": round(churn_rate_pct, 1),
            "risk_summary": f"Detected {churn_count} churn signals in {total} reviews.",
        }