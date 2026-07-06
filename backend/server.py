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
    button{cursor:pointer;background:#2563eb;color:white}
    input{width:420px;max-width:90%;background:#111827;color:white}
    pre{white-space:pre-wrap;background:#111827;border:1px solid #334155;border-radius:10px;padding:16px;min-height:160px}
    .row{margin:12px 0}.muted{color:#93a4bd}
  </style>
</head>
<body>
  <h1>QFin Backend Debug Tester</h1>
  <p class="muted">Use this page to test backend logic without Lovable UI.</p>

  <div class="row">
    <button onclick="health()">Test /health</button>
    <button onclick="chat('hello')">Test hello</button>
  </div>

  <div class="row">
    <input id="msg" value="analyze Microsoft" />
    <button onclick="chat(document.getElementById('msg').value)">Test /chat/stream</button>
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
  show('Loading chat...');
  try{
    const r=await fetch('/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message})});
    show(await r.text());
  }catch(e){ show('ERROR: '+e.message); }
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
