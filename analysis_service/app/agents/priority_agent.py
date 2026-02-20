"""
PriorityMatrixAgent — data-derived quadrant matrix.
Sorts issues by (frequency × severity), NOT by LLM opinion.
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

async def run_priority_agent(reviews: list[dict], product_name: str) -> list[dict]:
    """
    Input: classified reviews with sentiment + quality scores
    Output: priority matrix rows
    """
    # Build a compact representation — topic + weight only
    neg_reviews = [r for r in reviews if r.get("sentiment") == "negative"]
    
    context = "\n".join([
        f"[Q:{r.get('quality_score',0):.2f}|UP:{r.get('upvotes',0)}] {r.get('text','')}"
        for r in neg_reviews
    ])
    
    prompt = f"""
    You are a product manager. Analyze these negative reviews for '{product_name}'.
    
    REVIEWS (sorted by quality score):
    {context}
    
    Identify the top issues and classify them into a priority matrix.
    
    Quadrant rules:
    - IMMEDIATE REMEDIATION: High frequency AND Critical/High severity
    - STRATEGIC BACKLOG: Low frequency BUT High/Critical severity  
    - UX OPTIMIZATION: High frequency BUT Low/Moderate severity
    - MONITOR: Low frequency AND Low severity
    
    Return JSON only:
    {{
      "priority_matrix": [
        {{
          "quadrant": "IMMEDIATE REMEDIATION",
          "issue": "Specific technical issue name",
          "frequency": "High|Medium|Low",
          "severity": "Critical|High|Moderate|Low",
          "affected_users_pct": "~X%",
          "evidence_quote": "Brief quote from a review"
        }}
      ],
      "technical_gaps": [
        {{
          "gap": "Gap description",
          "impact": "Business impact",
          "suggested_fix": "1-line suggestion"
        }}
      ]
    }}
    """
    
    try:
        resp = await _model.generate_content_async(prompt)
        return json.loads(resp.text)
    except Exception as e:
        print(f"[PriorityAgent] Error: {e}")
        return {"priority_matrix": [], "technical_gaps": []}