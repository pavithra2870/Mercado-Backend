"""
Semantic deduplication + recency weighting.
Embeds all reviews, clusters near-duplicates, returns WeightedClusters.
"""
import os
import numpy as np
from datetime import datetime, timezone
from sklearn.cluster import DBSCAN
from dotenv import load_dotenv
from sklearn.preprocessing import normalize
from sentence_transformers import SentenceTransformer
from .models import ReviewItem

model = SentenceTransformer('all-MiniLM-L6-v2')

def _days_old(date_str: str) -> float:
    """Parse date string and return days since posting."""
    try:
        if date_str in ("unknown", "recent", ""):
            return 30.0  # default assumption
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        return max(delta.days, 0)
    except Exception:
        return 30.0

def recency_weight(days: float, lam: float = 0.005) -> float:
    """Exponential decay: w = e^(-λ × days). Recent = ~1.0, 6-month-old = ~0.4."""
    return float(np.exp(-lam * days))

def deduplicate_and_weight(reviews: list[ReviewItem]) -> list[dict]:
    """
    1. Embed all reviews via Gemini
    2. DBSCAN cluster by cosine similarity
    3. For each cluster: keep representative + compute weight
    Returns list of WeightedCluster dicts.
    """
    if not reviews:
        return []
    
    texts = [r.text for r in reviews]  # truncate for embedding efficiency
    
    # Batch embed
    print(f"[Dedup] Embedding {len(texts)} reviews locally using HuggingFace...")
    try:
        # Run local embedding
        embeddings = model.encode(texts, show_progress_bar=False)
    except Exception as e:
        print(f"[Dedup] Local embedding failed: {e}. Skipping dedup.")
        # Fallback: return all reviews as individual clusters
        return [
            {
                "cluster_id": i,
                "representative_text": r.text,
                "cluster_size": 1,
                "source": r.source,
                "recency_weight": recency_weight(_days_old(r.date)),
                "combined_weight": 1.0 * recency_weight(_days_old(r.date)),
                "sources": [r.source],
                "upvotes": r.upvotes,
            }
            for i, r in enumerate(reviews)
        ]
    
    # Normalize for cosine similarity
    embeddings_norm = normalize(embeddings, norm="l2")
    
    # DBSCAN clustering
    # eps=0.15 means reviews within 15% cosine distance are the same complaint
    db = DBSCAN(eps=0.07, min_samples=2, metric="cosine")
    labels = db.fit_predict(embeddings_norm)
    
    clusters = {}
    for idx, label in enumerate(labels):
        actual_label = label if label != -1 else f"noise_{idx}"
        if actual_label not in clusters:
            clusters[actual_label] = []
        clusters[actual_label].append(idx)
    weighted_clusters = []
    for label, indices in clusters.items():
        # Pick the review with most upvotes as representative
        best_idx = max(indices, key=lambda i: reviews[i].upvotes)
        representative = reviews[best_idx]
        
        # Compute weights
        days_list = [_days_old(reviews[i].date) for i in indices]
        avg_days = np.mean(days_list)
        r_weight = recency_weight(avg_days)
        size = len(indices)
        
        weighted_clusters.append({
            "cluster_id": label,
            "representative_text": representative.text,
            "cluster_size": size,
            "source": representative.source,
            "recency_weight": round(r_weight, 4),
            "combined_weight": round(size * r_weight, 4),
            "sources": list({reviews[i].source for i in indices}),
            "upvotes": sum(reviews[i].upvotes for i in indices),
        })
    
    # Sort by combined weight descending (most important first)
    weighted_clusters.sort(key=lambda x: x["combined_weight"], reverse=True)
    
    print(f"[Dedup] {len(reviews)} reviews → {len(weighted_clusters)} unique clusters")
    return weighted_clusters