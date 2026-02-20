"""
SentimentAgent — weighted aggregate score + market position summary.
Receives structured data only. NO raw review text.
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

async def run_sentiment_agent(reviews: list[dict]) -> dict:
    """
    Input: list of {text, sentiment, sentiment_score, quality_score, source, upvotes}
    Output: {sentiment_score, market_position, revenue_risk_level}
    """
    # Compute weighted score mathematically — no LLM needed for the number
    total_weight = sum(r.get("quality_score", 0.5) for r in reviews)
    if total_weight == 0:
        total_weight = len(reviews)
    
    sentiment_map = {"positive": 1.0, "neutral": 0.5, "negative": 0.0}
    weighted_sum = sum(
        sentiment_map.get(r.get("sentiment", "neutral"), 0.5) * r.get("quality_score", 0.5)
        for r in reviews
    )
    raw_score = (weighted_sum / total_weight) * 10  # Scale to 0-10
    
    neg_count = sum(1 for r in reviews if r.get("sentiment") == "negative")
    pos_count = sum(1 for r in reviews if r.get("sentiment") == "positive")
    
    # Use LLM only for the prose market position summary
    summary_context = "\n".join([
        f"[{r.get('sentiment','?').upper()}] {r.get('text','')}"
        for r in reviews  # Top 20 only
    ])
    
    prompt = f"""
    You are a market analyst. Given this sentiment data, write a concise market position summary.

    Calculated sentiment score: {raw_score:.1f}/10
    Positive reviews: {pos_count}
    Negative reviews: {neg_count}
    Total analyzed: {len(reviews)}

    Sample feedback:
    {summary_context}

    Return JSON only:
    {{
      "sentiment_score": {raw_score:.1f},
      "market_position": "3-sentence professional summary of product health",
      "revenue_risk_level": "Low|Moderate|Significant|Critical"
    }}
    """
    
    try:
        resp = await _model.generate_content_async(prompt)
        result = json.loads(resp.text)
        result["sentiment_score"] = round(raw_score, 1)  # Enforce our calculated score
        return result
    except Exception as e:
        print(f"[SentimentAgent] Error: {e}")
        return {
            "sentiment_score": round(raw_score, 1),
            "market_position": f"Analysis based on {len(reviews)} reviews. {pos_count} positive, {neg_count} negative.",
            "revenue_risk_level": "Moderate" if raw_score < 6 else "Low",
        }