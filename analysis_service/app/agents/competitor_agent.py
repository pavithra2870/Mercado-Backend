import os
import json
import logging
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from exa_py import Exa
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Setup Production Logging
logger = logging.getLogger("CompetitorAgent")
logger.setLevel(logging.INFO)

# --- Pydantic Schemas for Guaranteed LLM Output ---

class ProductContext(BaseModel):
    category: str = Field(description="The specific industry category, e.g., 'Project Management Software'")
    competitor_name: str = Field(description="The single biggest market rival mentioned or inferred")
    reasoning: str = Field(description="Why this category and competitor were chosen")

class CompetitorBenchmark(BaseModel):
    competitor_name: str
    metrics: List[str] = Field(description="Exactly 5 distinct performance/feature metrics relevant to the category")
    our_scores: List[int] = Field(description="Scores out of 10 for our product, matching the metrics array")
    competitor_scores: List[int] = Field(description="Scores out of 10 for the competitor, matching the metrics array")
    data_quality: str = Field(description="Enum: 'high_confidence', 'medium_confidence', or 'low_confidence'")
    key_differentiators: List[str] = Field(description="2 to 3 specific features that separate the products")

# --- Configuration ---

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
_exa = Exa(api_key=os.getenv("EXA_API_KEY"))

# Note: Using gemini-2.5-flash as requested. 
# We don't need "application/json" mime type here because passing the Pydantic schema handles it.
_model = genai.GenerativeModel("gemini-2.5-flash")


async def _identify_product_context(product_name: str, reviews: List[Dict[str, Any]]) -> ProductContext:
    """
    Determines category and competitor using strict Pydantic structured output.
    """
    # Dynamically limit context to roughly 3000 chars to save tokens while retaining signal
    context_text = "\n".join([r.get("text", "")[:250] for r in reviews[:12]])
    
    prompt = f"""
    Analyze these user reviews for the product '{product_name}'.
    
    1. Identify the specific Industry Category.
    2. Identify the Primary Competitor. If users mention one, use it. If not, infer the single biggest market rival based on the category.
    
    Reviews:
    {context_text}
    """
    
    try:
        # Prod-grade: Enforcing the schema directly in the API call
        resp = await _model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=ProductContext,
                temperature=0.1 # Low temperature for factual extraction
            )
        )
        return ProductContext.model_validate_json(resp.text)
    except Exception as e:
        logger.error(f"Context identification failed: {e}")
        return ProductContext(
            category="General Software", 
            competitor_name="Market Leader", 
            reasoning="Fallback due to generation error."
        )


async def _fetch_comparison_intel(product: str, competitor: str, category: str) -> str:
    """
    Uses Exa's Neural search to find deep, comparative intelligence.
    """
    # Neural prompt: Frame it as the sentence you want the article to contain
    neural_query = f"A detailed, unbiased comparison of {product} vs {competitor} for {category}, discussing pros, cons, and pricing."
    logger.info(f"Searching web with Neural Query: {neural_query}")

    try:
        result = _exa.search_and_contents(
            neural_query,
            type="auto", # Balances exact keywords with semantic meaning
            num_results=3,
            text={"max_characters": 1500}, # Cap length to save LLM context
            highlights={"num_sentences": 4, "highlights_per_url": 1},
            livecrawl="fallback" # Save credits if Exa already crawled a good comparison recently
        )
        
        snippets = []
        for r in result.results:
            # Prioritize highlights (the most relevant part of the page)
            content = r.highlights[0] if r.highlights else r.text
            snippets.append(f"Source: {r.title}\nInsights: {content}")
            
        return "\n---\n".join(snippets)
        
    except Exception as e:
        logger.error(f"Exa search failed: {e}")
        return ""


async def run_competitor_agent(reviews: List[Dict[str, Any]], product_name: str) -> dict:
    """
    Full Pipeline returning a guaranteed dictionary structure for the PDF generator.
    """
    logger.info(f"Starting Competitor Analysis for: {product_name}")
    
    # 1. Get Context
    context = await _identify_product_context(product_name, reviews)
    logger.info(f"Identified Category: {context.category} | Rival: {context.competitor_name}")

    # 2. Get Live Comparison Data
    comparison_data = ""
    if context.competitor_name and context.competitor_name.lower() != "market leader":
        comparison_data = await _fetch_comparison_intel(product_name, context.competitor_name, context.category)
    
    # 3. Final Scoring
    review_sample = "\n".join([r.get("text", "")[:300] for r in reviews[:15]])
    
    score_prompt = f"""
    Act as a Product Strategy Consultant. Perform a competitive benchmark.
    
    Product: {product_name}
    Competitor: {context.competitor_name}
    Category: {context.category}
    
    Data Source 1 (User Reviews of {product_name}):
    {review_sample}
    
    Data Source 2 (Web Comparisons):
    {comparison_data}
    
    Task: Score both products on 5 specific metrics relevant to {context.category} based on the provided data.
    """
    
    try:
        resp = await _model.generate_content_async(
            score_prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=CompetitorBenchmark,
                temperature=0.3 # Slight creativity allowed for metric naming
            )
        )
        benchmark = CompetitorBenchmark.model_validate_json(resp.text)
        return benchmark.model_dump()
        
    except Exception as e:
        logger.error(f"Scoring generation failed: {e}")
        # Prod-grade fallback: Ensure the PDF generator never crashes
        fallback = CompetitorBenchmark(
            competitor_name=context.competitor_name,
            metrics=["Performance", "Value", "Reliability", "Ease of Use", "Support"],
            our_scores=[5, 5, 5, 5, 5],
            competitor_scores=[5, 5, 5, 5, 5],
            data_quality="low_confidence",
            key_differentiators=["Insufficient comparison data gathered."]
        )
        return fallback.model_dump()