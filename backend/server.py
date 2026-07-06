import json
import re

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
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


@app.get('/debug/quick-chat')
async def debug_quick_chat(message: str = "analyze Microsoft"):
    ticker = base.resolve_ticker(message)
    greeting = _is_greeting(message)
    return {
        "status": "ok",
        "mode": "fast_debug_no_qwen_no_yfinance",
        "message_received": message,
        "is_greeting": greeting,
        "resolved_ticker": None if greeting else ticker,
        "would_use_market_data": False if greeting else bool(ticker),
        "would_call_qwen": False,
        "fast_answer": QFIN_GREETING if greeting else f"QFin understood the request. Resolved ticker: {ticker or 'not found'}. Full analysis route may be slow because it calls Yahoo/yfinance and Qwen.",
        "next_test": "Use /market-data/{ticker} only after ticker resolution works. Use /chat/stream only for final full AI test."
    }


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
    button{cursor:pointer;background:#2563eb;color:white}.fast{background:#16a34a}.slow{background:#b45309}
    input{width:420px;max-width:90%;background:#111827;color:white}
    pre{white-space:pre-wrap;background:#111827;border:1px solid #334155;border-radius:10px;padding:16px;min-height:160px}
    .row{margin:12px 0}.muted{color:#93a4bd}.warn{color:#ffb84d}
  </style>
</head>
<body>
  <h1>QFin Backend Debug Tester</h1>
  <p class="muted">Use this page to test backend logic without Lovable UI.</p>
  <p class="warn">Use the green fast button first. The orange full AI button can be slow because it calls Yahoo/yfinance + Qwen.</p>

  <div class="row">
    <button onclick="health()">Test /health</button>
    <button onclick="chat('hello')">Test hello</button>
  </div>

  <div class="row">
    <input id="msg" value="analyze Microsoft" />
    <button class="fast" onclick="quickChat()">Fast logic test</button>
    <button class="slow" onclick="chat(document.getElementById('msg').value)">Full AI /chat/stream</button>
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
async function withTimeout(url, options={}, ms=45000){
  const controller = new AbortController();
  const id = setTimeout(()=>controller.abort(), ms);
  try { return await fetch(url, {...options, signal: controller.signal}); }
  finally { clearTimeout(id); }
}
async function health(){
  try{ const r=await withTimeout('/health',{},10000); show(await r.json()); }catch(e){ show('ERROR: '+e.message); }
}
async function quickChat(){
  const message=document.getElementById('msg').value;
  show('Running fast logic test...');
  try{ const r=await withTimeout('/debug/quick-chat?message='+encodeURIComponent(message),{},10000); show(await r.json()); }catch(e){ show('ERROR: '+e.message); }
}
async function chat(message){
  show('Loading full AI chat. This can be slow. Timeout is 45 seconds...');
  try{
    const r=await withTimeout('/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message})},45000);
    show(await r.text());
  }catch(e){ show('TIMEOUT OR ERROR: '+e.message+'\nUse Fast logic test first. Full AI may be stuck on Yahoo/yfinance or Qwen.'); }
}
async function marketData(){
  const t=document.getElementById('ticker').value;
  show('Loading market data '+t+'...');
  try{ const r=await withTimeout('/market-data/'+encodeURIComponent(t),{},45000); show(await r.json()); }catch(e){ show('TIMEOUT OR ERROR: '+e.message); }
}
async function news(){
  const c=document.getElementById('cat').value;
  show('Loading news '+c+'...');
  try{ const r=await withTimeout('/community/news/'+encodeURIComponent(c),{},45000); show(await r.json()); }catch(e){ show('TIMEOUT OR ERROR: '+e.message); }
}
async function newsAlias(){
  const c=document.getElementById('cat').value;
  show('Loading news alias '+c+'...');
  try{ const r=await withTimeout('/news/'+encodeURIComponent(c),{},45000); show(await r.json()); }catch(e){ show('TIMEOUT OR ERROR: '+e.message); }
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
