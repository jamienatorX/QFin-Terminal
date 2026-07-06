import json
import re

from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel

import main as base
from news_module import generate_news, normalize_category

app = base.app

QFIN_GREETING = "Hello, I am QFin Terminal, your AI financial analyst and quantitative finance agent. You are welcome to ask me to analyze a company, compare stocks, explain financial ratios, build a valuation view, review risks, generate market news, or answer quant finance questions such as CAPM, VaR, portfolio optimization, options Greeks, and Monte Carlo simulation. Try: analyze Microsoft, analyze TSLA, compare Nvidia and AMD, explain VaR, or show Crypto news."

class CommunityNewsRequest(BaseModel):
    category: str = "Stocks"


def _extract_text(payload: dict) -> str:
    for key in ("message", "query", "prompt", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    messages = payload.get("messages")
    if isinstance(messages, list) and messages:
        for item in reversed(messages):
            if isinstance(item, dict) and isinstance(item.get("content"), str):
                return item["content"].strip()
    return ""


def _is_greeting(text: str) -> bool:
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    words = set(cleaned.split())
    if cleaned.strip() in {"", "hi", "hello", "hey", "helo"}:
        return True
    if words & {"hi", "hello", "hey", "helo"} and not (words & {"analyze", "analyse", "compare", "valuation", "stock", "ticker", "revenue", "profit", "risk", "capm", "var", "dcf"}):
        return True
    return False


@app.middleware("http")
async def qfin_greeting_guard(request: Request, call_next):
    if request.url.path in {"/chat", "/chat/stream", "/analyze"} and request.method == "POST":
        body = await request.body()
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            payload = {}
        text = _extract_text(payload)
        if _is_greeting(text):
            if request.url.path == "/chat/stream":
                return PlainTextResponse(QFIN_GREETING)
            return JSONResponse({"id": "qfin-greeting", "role": "assistant", "content": QFIN_GREETING, "answer": QFIN_GREETING, "data": {"qwen_status": "skipped_fast_reply", "used_live_data": False}})
        request._body = body
    return await call_next(request)


@app.get('/community/news/{category}')
async def community_news(category: str):
    return await generate_news(normalize_category(category))


@app.post('/community/news')
async def community_news_post(payload: CommunityNewsRequest):
    return await generate_news(normalize_category(payload.category))


@app.get('/news/{category}')
async def news(category: str):
    return await generate_news(normalize_category(category))


@app.post('/news')
async def news_post(payload: CommunityNewsRequest):
    return await generate_news(normalize_category(payload.category))
