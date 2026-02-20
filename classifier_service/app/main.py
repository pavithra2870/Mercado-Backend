from fastapi import FastAPI
from .models import ClassifyRequest, ClassifyResponse
from .classifier import classify_reviews
# FIXED: Only import aggregation, not scoring (classifier does scoring now)
from .sentiment import aggregate_sentiment

app = FastAPI(title="Classifier Service")

@app.post("/classify", response_model=ClassifyResponse)
async def classify(req: ClassifyRequest):
    print(f"[Main] Processing {len(req.reviews)} reviews for job {req.job_id}")

    # Step 1: Run the full Hybrid Pipeline (Filter -> Compress -> Verify -> Score)
    # clean is a list of ClassifiedReview objects (which ALREADY have sentiment data)
    clean, rejected = classify_reviews(req.reviews, req.product_name)
    # Step 2: Calculate Aggregate Stats (Math only, no AI)
    if clean:
        scores_list = [(r.sentiment, r.sentiment_score) for r in clean]
        weights = [r.quality_score for r in clean]
        sentiment_summary = aggregate_sentiment(scores_list, weights)
    else:
        # Fallback if everything was rejected
        sentiment_summary = aggregate_sentiment([], [])

    print(
        f"[Main] Success: {len(clean)} accepted, {rejected} rejected | "
        f"Score: {sentiment_summary['weighted_score']}/10"
    )

    return ClassifyResponse(
        job_id=req.job_id,
        reviews=clean,
        rejected_count=rejected,
        sentiment_summary=sentiment_summary,
    )

@app.get("/health")
def health():
    return {"status": "ok"}