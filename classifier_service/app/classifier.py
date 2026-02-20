"""
Review quality classifier — Hybrid Local + Cloud approach.

Pipeline:
1. Hard Filters (Regex/Heuristics) -> Local CPU
2. Summarization (Compression) -> Local CPU (DistilBART)
3. Relevance Verification -> Cloud API (Groq Llama-3)
4. Sentiment Scoring -> Local CPU (RoBERTa)
"""
import os
os.environ["HF_HOME"] = os.path.join(os.getcwd(), "hf_cache")
import re
import json
from groq import Groq
from transformers import pipeline
from .models import RawReview, ClassifiedReview
from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
from dotenv import load_dotenv
load_dotenv()
# ── CONFIGURATION ──────────────────────────────────────────────────────────
# We use DistilBART because it is 40% smaller and 50% faster than standard BART
SUMMARIZATION_MODEL = "sshleifer/distilbart-cnn-12-6"
GROQ_MODEL = "llama-3.1-8b-instant"  # Fast, cheap, smart enough for classification

# ── MODEL LOADING ──────────────────────────────────────────────────────────
print("[Classifier] Loading sentiment model...")
_sentiment_pipe = pipeline(
    "text-classification",
    model="cardiffnlp/twitter-roberta-base-sentiment-latest",
    top_k=1,
    truncation=True,
    max_length=512,
)

print(f"[Classifier] Loading summarization model ({SUMMARIZATION_MODEL})...")
# Device=-1 forces CPU. If you have GPU, change to device=0
# METHOD 2: Direct Loading (Bypasses "Unknown task" error)
try:
    _tokenizer = AutoTokenizer.from_pretrained(SUMMARIZATION_MODEL)
    _summ_model = AutoModelForSeq2SeqLM.from_pretrained(SUMMARIZATION_MODEL)
except Exception as e:
    print(f"FATAL: Model loading failed. {e}")
    raise e

# Initialize Groq Client
_groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

print("[Classifier] All models loaded.")

# ── SPAM PATTERNS (The "Cheap" Filter) ─────────────────────────────────────
SPAM_PATTERNS = [
    r"\b(buy now|click here|discount|promo code|affiliate|sponsored)\b",
    r"https?://\S+",
    r"\b(dm me|contact me at)\b",
]
SPAM_RE = re.compile("|".join(SPAM_PATTERNS), re.IGNORECASE)

# ── HELPER FUNCTIONS ───────────────────────────────────────────────────────

def _quality_score(text: str, upvotes: int, source: str) -> float:
    # (Same logic as before - omitted for brevity, assume it exists)
    # ... [Keep your original _quality_score function here] ...
    length = len(text.strip())
    score = 0.1 if length > 50 else 0.0
    if upvotes > 10: score += 0.2
    return min(score + 0.5, 1.0) # Simplified for this example

def _summarize_local(texts: list[str]) -> list[str]:
    """
    Compresses long texts into short summaries locally.
    """
    summaries = []
    for text in texts:
        if len(text.split()) < 60:
            summaries.append(text)
            continue
            
        try:
            # Explicit generation call instead of pipeline
            inputs = _tokenizer(text, return_tensors="pt", max_length=1024, truncation=True)
            
            # Generate summary IDs
            summary_ids = _summ_model.generate(
                inputs["input_ids"], 
                max_length=60, 
                min_length=10, 
                do_sample=False
            )
            
            # Decode back to text
            summary = _tokenizer.decode(summary_ids[0], skip_special_tokens=True)
            summaries.append(summary)
        except Exception as e:
            print(f"[Classifier] Summarization failed: {e}")
            summaries.append(text[:200]) 
            
    return summaries

def _verify_with_groq(summaries: list[str], product_name: str) -> list[bool]:
    """
    Sends SUMMARIES (not raw text) to Groq to decide relevance.
    """
    if not summaries:
        return []

    # DYNAMIC PROMPT
    prompt = f"""
    You are a Data Filtering AI for a product called "{product_name}".
    
    Task: Analyze the following list of review summaries.
    Return a JSON object with a single key "decisions" containing a list of booleans.
    
    - true: The review is relevant to "{product_name}" (software, features, bugs, pricing, or use cases).
    - false: The review is about Politics, Video Games, completely different products, Spam lists, or totally unrelated topics.
    
    Summaries to check:
    {json.dumps(summaries)}
    
    Output JSON ONLY. No yapping.
    """

    try:
        chat_completion = _groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=GROQ_MODEL,
            response_format={"type": "json_object"},
        )
        result = json.loads(chat_completion.choices[0].message.content)
        # Fallback if LLM returns fewer decisions than inputs
        decisions = result.get("decisions", [])
        if len(decisions) != len(summaries):
            return [True] * len(summaries)
        return decisions
    except Exception as e:
        print(f"[Classifier] Groq verification failed: {e}")
        return [True] * len(summaries)

# ... [_quality_score and _summarize_local remain the same] ...

def classify_reviews(reviews: list[RawReview], product_name: str, min_quality: float = 0.15) -> tuple[list[ClassifiedReview], int]:
    clean = []
    rejected = 0
    
    # 1. PHASE 1: PRE-FILTER
    candidates = []
    for r in reviews:
        if SPAM_RE.search(r.text):
            rejected += 1
            continue
        if len(r.text) < 10:
            rejected += 1
            continue
        candidates.append(r)
        
    if not candidates:
        return [], rejected

    print(f"[Classifier] Phase 1 passed: {len(candidates)} candidates.")

    # 2. PHASE 2: COMPRESSION
    candidate_texts = [r.text for r in candidates]
    summaries = _summarize_local(candidate_texts)
    
    # 3. PHASE 3: VERIFICATION (Dynamic)
    print(f"[Classifier] Verifying relevance for '{product_name}'...")
    # PASS PRODUCT NAME HERE
    decisions = _verify_with_groq(summaries, product_name)
    
    verified_reviews = []
    for i, decision in enumerate(decisions):
        if decision:
            verified_reviews.append(candidates[i])
        else:
            rejected += 1
            print(f"[Classifier] Groq rejected: {summaries[i][:50]}...")

    if not verified_reviews:
        return [], rejected

    # 4. PHASE 4: SENTIMENT
    final_texts = [r.text[:512] for r in verified_reviews]
    try:
        sentiment_results = _sentiment_pipe(final_texts, batch_size=8)
    except Exception:
        sentiment_results = [[{"label": "neutral", "score": 0.5}]] * len(verified_reviews)

    # 5. CONSTRUCT OUTPUT
    for i, review in enumerate(verified_reviews):
        res = sentiment_results[i]
        top = res[0] if isinstance(res, list) else res
        
        q_score = _quality_score(review.text, review.upvotes, review.source)
        
        clean.append(ClassifiedReview(
            **review.model_dump(),
            is_genuine=True,
            quality_score=round(q_score, 3),
            sentiment=top.get("label", "neutral"),
            sentiment_score=round(top.get("score", 0.5), 3),
        ))

    return clean, rejected