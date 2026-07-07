import asyncio
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from news_sources import CATEGORY_QUERIES, fetch_all_sources
from qwen_client import QwenClientError, call_qwen, qwen_is_configured

VALID_CATEGORIES = {"Crypto", "Stocks", "Bonds", "ETFs", "Other"}

NEWS_SYSTEM_PROMPT = """
You are QFin News, the market news engine for QFin Terminal. Respond only with valid JSON.
Return one JSON object for the selected category with exactly 5 market-moving news cards.
Do not return prose, markdown fences, or commentary.
Use only the provided candidate articles when naming sources or links. Never fabricate a source URL.
If live candidates are weak or missing, create stale fallback cards and set stale true.
Headlines must be under 8 words. Sentiment must be positive, negative, or neutral based on likely market impact.
Each item must include id, headline, sentiment, teaser, explanation, and source.
Explanation must include what_happened, why_it_matters, and market_reaction.
Only include data when numeric information is clearly provided. Otherwise omit data.
Schema: {"category":"Crypto","generated_at":"ISO_TIME","news":[{"id":"1","headline":"...","sentiment":"positive","teaser":"...","explanation":{"what_happened":"...","why_it_matters":"...","market_reaction":"..."},"source":{"name":"...","url":"..."}}]}
""".strip()

def normalize_category(category: str) -> str:
    raw = (category or "Stocks").strip().lower()
    mapping = {"crypto": "Crypto", "stocks": "Stocks", "stock": "Stocks", "bonds": "Bonds", "bond": "Bonds", "etfs": "ETFs", "etf": "ETFs", "other": "Other"}
    return mapping.get(raw, "Stocks")

def clean_json(raw: str) -> str:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned

def build_source(item: Dict[str, Any]) -> Dict[str, str]:
    name = item.get("publisher") or item.get("source") or "Aggregated market commentary"
    link = item.get("link") or item.get("url")
    source = {"name": str(name)}
    if link:
        source["url"] = str(link)
    return source

async def fetch_news_candidates(category: str) -> List[Dict[str, Any]]:
    return await fetch_all_sources(category)

def fallback_news(category: str, candidates: Optional[List[Dict[str, Any]]] = None, parse_failure: bool = False) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    items = []
    candidates = candidates or []
    for i in range(5):
        if i < len(candidates) and candidates[i].get("title"):
            title = str(candidates[i].get("title"))
            headline = " ".join(title.split()[:7])
            summary = candidates[i].get("summary") or title
            source = build_source(candidates[i])
            stale = False
        else:
            headline = f"{category} Market Update"
            summary = "Live news retrieval was limited, so QFin is showing a fallback market card."
            source = {"name": "Aggregated market commentary"}
            stale = True
        items.append({
            "id": str(i + 1),
            "headline": headline,
            "sentiment": "neutral",
            "teaser": str(summary)[:180],
            "explanation": {
                "what_happened": str(summary)[:240],
                "why_it_matters": "This item may affect market sentiment, positioning, or risk appetite in the selected category.",
                "market_reaction": "Specific price or volume reaction is unavailable from the current backend source."
            },
            "source": source,
            "stale": stale,
        })
    output = {"category": category, "generated_at": now, "news": items}
    if parse_failure:
        output["error"] = "parse_failure"
    return output

def validate_news(parsed: Dict[str, Any], category: str) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        raise ValueError("News response is not an object")
    news = parsed.get("news")
    if not isinstance(news, list) or len(news) == 0:
        raise ValueError("Empty or malformed news array")
    parsed["category"] = category
    parsed["generated_at"] = parsed.get("generated_at") or datetime.now(timezone.utc).isoformat()
    parsed["news"] = news[:5]
    for idx, item in enumerate(parsed["news"]):
        item["id"] = str(item.get("id") or idx + 1)
        item["sentiment"] = item.get("sentiment") if item.get("sentiment") in {"positive", "negative", "neutral"} else "neutral"
        item["headline"] = str(item.get("headline") or f"{category} Update")[:70]
        item["teaser"] = str(item.get("teaser") or item["headline"])
        if not isinstance(item.get("explanation"), dict):
            item["explanation"] = {"what_happened": item["teaser"], "why_it_matters": "Market impact requires more context.", "market_reaction": "Market reaction unavailable."}
        if not isinstance(item.get("source"), dict):
            item["source"] = {"name": "Aggregated market commentary"}
    while len(parsed["news"]) < 5:
        parsed["news"].append(fallback_news(category)["news"][len(parsed["news"])])
    return parsed

async def generate_news(category: str) -> Dict[str, Any]:
    category = normalize_category(category)
    try:
        candidates = await asyncio.wait_for(fetch_news_candidates(category), timeout=5)
    except Exception:
        candidates = []
    if not qwen_is_configured():
        return fallback_news(category, candidates)
    model = os.getenv("DASHSCOPE_NEWS_MODEL", "qwen-plus")
    if "thinking" in model.lower():
        model = "qwen-plus"
    user = {"category": category, "generated_at": datetime.now(timezone.utc).isoformat(), "candidate_articles": candidates[:25], "instruction": "Generate the top 5 news items. Return only valid JSON matching the schema."}
    try:
        response = await asyncio.wait_for(
            call_qwen(
                messages=[{"role": "system", "content": NEWS_SYSTEM_PROMPT}, {"role": "user", "content": "JSON input: " + json.dumps(user, ensure_ascii=False)}],
                model=model,
                response_format={"type": "json_object"},
                temperature=0.1,
            ),
            timeout=8,
        )
        raw = response["choices"][0]["message"]["content"]
        parsed = json.loads(clean_json(raw))
        return validate_news(parsed, category)
    except (QwenClientError, KeyError, IndexError, json.JSONDecodeError, ValueError, asyncio.TimeoutError):
        return fallback_news(category, candidates, parse_failure=True)
