import asyncio
import json
import re
import time
from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel

import main as base
from news_module import generate_news, normalize_category

app = base.app

QFIN_GREETING = "Hello, I am QFin Terminal, your AI financial analyst and quantitative finance agent. You are welcome to ask me to analyze a company, compare stocks, explain financial ratios, build a valuation view, review risks, generate market news, or answer quant finance questions such as CAPM, VaR, portfolio optimization, options Greeks, and Monte Carlo simulation. Try: analyze Microsoft, analyze TSLA, compare Nvidia and AMD, explain VaR, or show Crypto news."

_DATA_CACHE: Dict[str, Dict[str, Any]] = {}
_DATA_CACHE_TTL_SECONDS = 600
_ALLOWED_ORIGINS = {
    "https://q-fin-terminal.vercel.app",
    "https://qfin-terminal.vercel.app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}

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


def _extract_ticker(payload: dict) -> Optional[str]:
    value = payload.get("ticker")
    return value.strip().upper() if isinstance(value, str) and value.strip() else None


def _is_greeting(text: str) -> bool:
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    words = set(cleaned.split())
    if cleaned.strip() in {"", "hi", "hello", "hey", "helo"}:
        return True
    if words & {"hi", "hello", "hey", "helo"} and not (words & {"analyze", "analyse", "compare", "valuation", "stock", "ticker", "revenue", "profit", "risk", "capm", "var", "dcf"}):
        return True
    return False


def _cors_headers(request: Request) -> Dict[str, str]:
    origin = request.headers.get("origin")
    allowed_origin = origin if origin in _ALLOWED_ORIGINS else "https://q-fin-terminal.vercel.app"
    return {
        "Access-Control-Allow-Origin": allowed_origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Headers": "content-type, authorization",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Vary": "Origin",
    }


async def _cached_financial_data(ticker: str):
    key = ticker.strip().upper()
    now = time.time()
    cached = _DATA_CACHE.get(key)
    if cached and now - cached["ts"] < _DATA_CACHE_TTL_SECONDS:
        return cached["data"], True
    data = await asyncio.to_thread(base.fetch_financial_data, key)
    _DATA_CACHE[key] = {"ts": now, "data": data}
    return data, False


async def _real_chat_stream(message: str, ticker: Optional[str] = None):
    started = time.time()
    quick = base.fast_casual_reply(message)
    if quick:
        yield quick
        return

    yield "QFin Terminal real analysis started.\n"
    yield "Step 1/3: resolving ticker...\n"
    resolved = base.resolve_ticker(message, ticker)
    yield f"Resolved ticker: {resolved or 'not found'}\n"

    data = None
    if base.wants_data(message, resolved) and resolved:
        yield "Step 2/3: fetching Yahoo/yfinance market data and financial statement data...\n"
        data, from_cache = await _cached_financial_data(resolved)
        yield f"Data fetch complete ({'cached' if from_cache else 'fresh'}).\n"
    else:
        yield "Step 2/3: no ticker data needed for this request.\n"

    if not base.qwen_is_configured():
        yield "\nQwen is not configured. Add DASHSCOPE_API_KEY in Render.\n"
        return

    yield "Step 3/3: calling Qwen for final QFin report...\n\n---\n\n"
    try:
        response = await base.call_qwen(base.build_prompt(message, resolved, data))
        content = base.clean_text(response["choices"][0]["message"]["content"])
        yield content
    except Exception as e:
        yield f"Qwen failed: {e}\n"
    yield f"\n\n---\nCompleted in {time.time() - started:.1f}s."


@app.middleware("http")
async def qfin_stream_guard(request: Request, call_next):
    if request.url.path == "/chat/stream" and request.method == "OPTIONS":
        return PlainTextResponse("", headers=_cors_headers(request))

    if request.url.path == "/chat/stream" and request.method == "POST":
        body = await request.body()
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            payload = {}
        message = _extract_text(payload) or "Hello"
        ticker = _extract_ticker(payload)
        if _is_greeting(message):
            return PlainTextResponse(QFIN_GREETING, headers=_cors_headers(request))
        return StreamingResponse(
            _real_chat_stream(message, ticker),
            media_type="text/plain; charset=utf-8",
            headers=_cors_headers(request),
        )

    if request.url.path in {"/chat", "/analyze"} and request.method == "POST":
        body = await request.body()
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            payload = {}
        text = _extract_text(payload)
        if _is_greeting(text):
            return JSONResponse({"id": "qfin-greeting", "role": "assistant", "content": QFIN_GREETING, "answer": QFIN_GREETING, "data": {"qwen_status": "skipped_fast_reply", "used_live_data": False}}, headers=_cors_headers(request))
        request._body = body
    return await call_next(request)


@app.get('/debug', response_class=HTMLResponse)
async def debug_page():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>QFin Backend Debug</title>
  <style>
    body{font-family:Arial,sans-serif;background:#0b1020;color:#eaf2ff;margin:24px;line-height:1.4}
    button,input,select{padding:10px;margin:6px;border-radius:8px;border:1px solid #334155}
    button{cursor:pointer;background:#2563eb;color:white}.real{background:#16a34a}
    input{width:420px;max-width:90%;background:#111827;color:white}
    pre{white-space:pre-wrap;background:#111827;border:1px solid #334155;border-radius:10px;padding:16px;min-height:260px}
    .row{margin:12px 0}.muted{color:#93a4bd}
  </style>
</head>
<body>
  <h1>QFin Backend Debug Tester</h1>
  <p class="muted">This tests the real backend output: yfinance data + Qwen report. It streams progress so it does not look frozen.</p>

  <div class="row">
    <button onclick="health()">Test /health</button>
    <button onclick="chat('hello')">Test hello</button>
  </div>

  <div class="row">
    <input id="msg" value="analyze Microsoft" />
    <button class="real" onclick="chat(document.getElementById('msg').value)">Real Qwen + yfinance output</button>
  </div>

  <div class="row">
    <input id="ticker" value="MSFT" style="width:120px" />
    <button onclick="marketData()">Test /market-data</button>
  </div>

  <div class="row">
    <select id="cat">
      <option>Stocks</option><option>Crypto</option><option>Bonds</option><option>ETFs</option><option>Other</option>
    </select>
    <button onclick="news()">Test /community/news</button>
    <button onclick="newsAlias()">Test /news alias</button>
  </div>

  <h3>Output</h3>
  <pre id="out">Waiting...</pre>

<script>
const out = document.getElementById('out');
function show(x){ out.textContent = typeof x === 'string' ? x : JSON.stringify(x,null,2); }
async function health(){
  try{ const r=await fetch('/health'); show(await r.json()); }catch(e){ show('ERROR: '+e.message); }
}
async function chat(message){
  out.textContent = '';
  try{
    const r=await fetch('/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message})});
    if(!r.body){ show(await r.text()); return; }
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    while(true){
      const part = await reader.read();
      if(part.done) break;
      out.textContent += decoder.decode(part.value,{stream:true});
    }
  }catch(e){ show('ERROR: '+e.message); }
}
async function marketData(){
  const t=document.getElementById('ticker').value;
  show('Loading market data '+t+'...');
  try{ const r=await fetch('/market-data/'+encodeURIComponent(t)); show(await r.json()); }catch(e){ show('ERROR: '+e.message); }
}
async function news(){
  const c=document.getElementById('cat').value;
  show('Loading news '+c+'...');
  try{ const r=await fetch('/community/news/'+encodeURIComponent(c)); show(await r.json()); }catch(e){ show('ERROR: '+e.message); }
}
async function newsAlias(){
  const c=document.getElementById('cat').value;
  show('Loading news alias '+c+'...');
  try{ const r=await fetch('/news/'+encodeURIComponent(c)); show(await r.json()); }catch(e){ show('ERROR: '+e.message); }
}
</script>
</body>
</html>
"""


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
