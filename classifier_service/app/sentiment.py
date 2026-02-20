"""
sentiment.py - Aggregation logic only.
Inference is now handled upstream in classifier.py.
"""

def aggregate_sentiment(scores_list: list[tuple[str, float]], weights: list[float]) -> dict:
    """
    Computes a weighted 0-10 sentiment score.
    Input: [('positive', 0.9), ('negative', 0.6)], [0.8, 0.5]
    """
    if not scores_list:
        return {
            "overall_label": "neutral",
            "weighted_score": 5.0,
            "positive_pct": 0.0,
            "neutral_pct": 0.0,
            "negative_pct": 0.0,
            "total": 0
        }

    # Map labels to values: Pos=1, Neu=0, Neg=-1
    # We use 0.5 for neutral to keep the baseline in the middle
    VAL_MAP = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
    
    weighted_sum = 0.0
    total_weight = 0.0
    
    counts = {"positive": 0, "neutral": 0, "negative": 0}
    
    for (label, conf), weight in zip(scores_list, weights):
        val = VAL_MAP.get(label, 0.0)
        
        # Formula: Value * Confidence * QualityWeight
        # Example: Positive(1.0) * Conf(0.9) * Quality(0.8) = 0.72 contribution
        contribution = val * conf * weight
        
        weighted_sum += contribution
        total_weight += weight
        counts[label] += 1
        
    # Normalize to -1 to +1
    if total_weight == 0:
        raw_score = 0.0
    else:
        raw_score = weighted_sum / total_weight
        
    # Scale -1..+1 to 0..10
    # -1 -> 0, 0 -> 5, +1 -> 10
    final_score = round(((raw_score + 1) / 2) * 10, 2)
    
    total = len(scores_list)
    return {
        "overall_label": max(counts, key=counts.get), # Label with highest count
        "weighted_score": final_score,
        "positive_pct": round(counts["positive"] / total * 100, 1),
        "neutral_pct": round(counts["neutral"] / total * 100, 1),
        "negative_pct": round(counts["negative"] / total * 100, 1),
        "total": total
    }