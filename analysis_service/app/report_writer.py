"""
ReportWriter — the ONE synthesis LLM call.
Receives fully structured AnalysisResult and writes professional Markdown.
"""
import os
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
_model = genai.GenerativeModel("gemini-2.5-flash")

async def write_report(product_name: str, analysis: dict, reviews: list[dict]) -> str:
    """
    Input: structured AnalysisResult dict + review list for evidence quotes
    Output: professional Markdown report string
    """
    # Build evidence index for citations
    evidence = "\n".join([
        f"{i+1:03}: [{r.get('source','?').upper()}] {r.get('text','')}"
        for i, r in enumerate(reviews[:30])
    ])
    
    priority_matrix = analysis.get("priority_matrix", [])
    tech_gaps = analysis.get("technical_gaps", [])
    competitor = analysis.get("competitor", {})
    risk = analysis.get("risk", {})
    sentiment_data = analysis.get("sentiment", {})
    
    prompt = f"""
    You are a Principal Consultant at a global strategy firm.
    Write a formal Market Intelligence Report for: "{product_name.upper()}"
    
    You have ALREADY been given the structured analysis below. Do NOT invent data.
    Write professional prose that references the data provided.
    
    ── STRUCTURED DATA (DO NOT CONTRADICT THIS) ──
    
    Sentiment Score: {sentiment_data.get('sentiment_score', 'N/A')}/10
    Market Position: {sentiment_data.get('market_position', '')}
    Revenue Risk: {sentiment_data.get('revenue_risk_level', '')}
    
    Priority Matrix:
    {priority_matrix}
    
    Technical Gaps:
    {tech_gaps}
    
    Competitor: {competitor.get('competitor_name', 'N/A')}
    Risk Summary: {risk.get('risk_summary', '')}
    Churn Signal Rate: {risk.get('churn_rate_pct', 0)}%
    
    ── EVIDENCE INDEX (cite as DATANODE_XXX) ──
    {evidence}
    
    ── OUTPUT FORMAT (strict Markdown) ──
    
    # MARKET INTELLIGENCE REPORT: {product_name.upper()}
    
    ## 1. EXECUTIVE OVERVIEW
    * **Aggregate Sentiment Metric:** [Use the provided score. Explain calculation methodology.]
    * **Current Market Position:** [Use provided market_position verbatim or expand it]
    * **Revenue Retention Risk:** [Use provided risk level]
    
    ## 2. CRITICAL PRODUCT FRICTION & TECHNICAL GAPS
    [Write one section per item in technical_gaps. Cite DATANODEs as evidence.]
    
    ## 3. PAIN-TO-PRIORITY MATRIX
    [Convert priority_matrix list into a proper Markdown table]
    
    ## 4. FINANCIAL & COMPETITIVE POSITIONING
    [Use competitor data + risk data. Be precise. Label estimates as estimates.]
    
    ## 5. STRATEGIC REMEDIATION ROADMAP
    [3 numbered recommendations derived from the priority matrix. Be specific.]
    """
    
    try:
        resp = await _model.generate_content_async(prompt)
        return resp.text
    except Exception as e:
        return f"# REPORT GENERATION ERROR\n\nError: {e}\n\nRaw analysis data:\n```json\n{analysis}\n```"