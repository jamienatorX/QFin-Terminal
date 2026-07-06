from dotenv import load_dotenv
load_dotenv()

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from qwen_client import QwenClientError, call_qwen, qwen_is_configured

app = FastAPI(title="QFin Terminal API", version="qfin-fast-chat-1.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

SYSTEM_PROMPT = """
You are QFin Terminal, a finance research assistant. You can chat normally, but you specialize in company analysis, financial statements, valuation, portfolio math, risk, derivatives, statistics, CAPM, DCF, VaR, factor models, options Greeks, and quantitative finance. Never invent company figures. Use backend data, user data, or clearly stated assumptions only. When data is missing, say it is missing. For company analysis, cover profitability, cash flow quality, balance sheet health, growth or efficiency, and key risks. For comparisons, compare side by side and explain structural differences. Do not give personal investment instructions. Use clear plain text and do not output JSON to the user.
""".strip()

class AnalyzeRequest(BaseModel):
    query: str
    ticker: Optional[str] = None
    mode: str = "full_report"

class ChatMessage(BaseModel):
    role: Optional[str] = "user"
    content: str

class ChatRequest(BaseModel):
    message: Optional[str] = None
    query: Optional[str] = None
    prompt: Optional[str] = None
    ticker: Optional[str] = None
    mode: Optional[str] = "chat"
    messages: Optional[List[ChatMessage]] = None

ALIASES = {
    "tesla": "TSLA", "alibaba": "BABA", "apple": "AAPL", "microsoft": "MSFT", "nvidia": "NVDA",
    "amazon": "AMZN", "google": "GOOGL", "alphabet": "GOOGL", "meta": "META", "netflix": "NFLX",
    "uber": "UBER", "grab": "GRAB"
}
STOP = {"AI", "API", "CEO", "CFO", "GDP", "CPI", "USD", "IDR", "THE", "AND", "YOU", "HELLO", "HI", "HEY", "OK", "YES", "NO"}
FIN_WORDS = ["analyze", "analyse", "compare", "stock", "ticker", "company", "financial", "finance", "revenue", "profit", "margin", "debt", "cash flow", "valuation", "price", "earnings", "risk", "market cap", "dcf", "capm", "portfolio", "option", "roe", "roa", "roic", "fcf"]
TICKER_RE = r"[A-Za-z0-9][A-Za-z0-9\.\-\^=]{0,17}"

CASUAL_REPLIES = {
    "hi": "Hi, I am QFin Terminal. You can ask me normal questions, but I specialize in company analysis, financial statements, valuation, and quantitative finance.",
    "hello": "Hello, I am QFin Terminal. Ask me to analyze a company, compare stocks, explain ratios, or answer quant finance questions.",
    "hey": "Hey, I am QFin Terminal. What company or finance topic do you want to look at?",
    "thanks": "You're welcome.",
    "thank you": "You're welcome.",
    "ok": "Okay.",
    "okay": "Okay."
}

def extract_chat_query(payload: ChatRequest) -> str:
    if payload.message: return payload.message
    if payload.query: return payload.query
    if payload.prompt: return payload.prompt
    if payload.messages:
        users = [m.content for m in payload.messages if (m.role or "user") == "user"]
        return users[-1] if users else payload.messages[-1].content
    return "Hello"

def clean_text(text: str) -> str:
    text = text.replace("**", "").replace("*", "").replace("#", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()

def normalize_user_text(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()

def fast_casual_reply(q: str) -> Optional[str]:
    normalized = normalize_user_text(q)
    if normalized in CASUAL_REPLIES:
        return CASUAL_REPLIES[normalized]
    if normalized in {"what can you do", "who are you", "help", "menu"}:
        return "I am QFin Terminal. I can chat normally, analyze public companies, resolve company names into tickers, fetch latest available Yahoo Finance data, explain financial statements, compare companies, and help with valuation or quant finance concepts. Try: analyze Microsoft, analyze Honda, analyze Bumi Resources, or compare TSLA and BYD."
    return None

def norm_symbol(s: str) -> str:
    s = s.strip().upper().strip(".,;:!?()[]{}\"'")
    return "BRK-B" if s == "BRK.B" else s

def finance_intent(q: str) -> bool:
    lower = q.lower()
    return any(w in lower for w in FIN_WORDS)

def yahoo_symbol_search(q: str) -> Optional[str]:
    try:
        cleaned = re.sub(r"\b(analyze|analyse|compare|check|review|research|stock|ticker|company|financial|finance|about|for|on|valuation|value)\b", " ", q, flags=re.I)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) < 2: return None
        r = httpx.get("https://query2.finance.yahoo.com/v1/finance/search", params={"q": cleaned, "quotesCount": 10, "newsCount": 0, "enableFuzzyQuery": True}, headers={"User-Agent": "Mozilla/5.0"}, timeout=8, follow_redirects=True)
        if r.status_code >= 400: return None
        for item in r.json().get("quotes", []):
            if item.get("symbol") and item.get("quoteType") in {"EQUITY", "ETF", "MUTUALFUND", "INDEX"}:
                return norm_symbol(item["symbol"])
    except Exception:
        return None
    return None

def resolve_ticker(q: str, provided: Optional[str] = None) -> Optional[str]:
    if provided: return norm_symbol(provided)
    lower = q.lower()
    cash = re.search(rf"\$({TICKER_RE})\b", q)
    if cash:
        c = norm_symbol(cash.group(1))
        if c not in STOP: return c
    for token in re.findall(r"\b(?:[0-9]{1,6}|[A-Z]{1,6})(?:[\.\-][A-Z0-9]{1,6}){1,2}\b", q):
        c = norm_symbol(token)
        if c not in STOP: return c
    for name, ticker in ALIASES.items():
        if re.search(rf"\b{re.escape(name)}\b", lower): return ticker
    if finance_intent(q):
        found = yahoo_symbol_search(q)
        if found: return found
    for token in re.findall(r"\b[A-Z]{1,5}(?:[\.-][A-Z])?\b", q):
        c = norm_symbol(token)
        if c not in STOP: return c
    first = re.search(rf"\b(?:analyze|analyse|check|review|research|about|stock|ticker|company|financials?|value|valuation)\s+({TICKER_RE})\b", q, re.I)
    if first:
        c = norm_symbol(first.group(1))
        if c not in STOP: return c
    return None

def wants_data(q: str, ticker: Optional[str]) -> bool:
    if not ticker: return False
    compact = re.sub(r"[^A-Za-z0-9\.\-\^=]", "", q).upper()
    return compact == ticker.upper() or finance_intent(q) or ticker.lower() in q.lower() or ticker.upper() in q.upper()

def as_float(v: Any) -> Optional[float]:
    try:
        if v is None: return None
        if hasattr(v, "item"): v = v.item()
        x = float(v)
        return None if x != x else x
    except Exception:
        return None

def money(v: Any, cur: str) -> Optional[str]:
    x = as_float(v)
    if x is None: return None
    if abs(x) >= 1_000_000_000_000: return f"{cur} {x/1_000_000_000_000:.2f}T"
    if abs(x) >= 1_000_000_000: return f"{cur} {x/1_000_000_000:.2f}B"
    if abs(x) >= 1_000_000: return f"{cur} {x/1_000_000:.2f}M"
    return f"{cur} {x:,.2f}"

def pct(v: Any) -> Optional[str]:
    x = as_float(v)
    if x is None: return None
    if abs(x) <= 3: x *= 100
    return f"{x:.2f}%"

def row(frame: Any, names: List[str]) -> Optional[float]:
    try:
        if frame is None or frame.empty: return None
        for name in names:
            if name in frame.index:
                s = frame.loc[name].dropna()
                if len(s) > 0: return as_float(s.iloc[0])
    except Exception:
        return None
    return None

def fetch_financial_data(ticker: str) -> Dict[str, Any]:
    try:
        import yfinance as yf
        asset = yf.Ticker(ticker)
        try: info = asset.get_info() or {}
        except Exception: info = {}
        try: fast = dict(asset.fast_info or {})
        except Exception: fast = {}
        try: hist = asset.history(period="5d", interval="1d", auto_adjust=False)
        except Exception: hist = None
        try: inc = asset.financials
        except Exception: inc = None
        try: bal = asset.balance_sheet
        except Exception: bal = None
        try: cf = asset.cashflow
        except Exception: cf = None
        cur = info.get("financialCurrency") or info.get("currency") or fast.get("currency") or "USD"
        price = as_float(fast.get("last_price") or info.get("currentPrice") or info.get("regularMarketPrice"))
        prev = as_float(fast.get("previous_close") or info.get("previousClose"))
        if hist is not None and not hist.empty and "Close" in hist:
            closes = hist["Close"].dropna()
            if len(closes) > 0 and price is None: price = as_float(closes.iloc[-1])
            if len(closes) > 1 and prev is None: prev = as_float(closes.iloc[-2])
        change = (price - prev) / prev if price is not None and prev not in (None, 0) else None
        revenue = as_float(info.get("totalRevenue")) or row(inc, ["Total Revenue", "Operating Revenue"])
        gp = as_float(info.get("grossProfits")) or row(inc, ["Gross Profit"])
        ni = as_float(info.get("netIncomeToCommon")) or row(inc, ["Net Income", "Net Income Common Stockholders"])
        ocf = as_float(info.get("operatingCashflow")) or row(cf, ["Operating Cash Flow", "Total Cash From Operating Activities"])
        fcf = as_float(info.get("freeCashflow")) or row(cf, ["Free Cash Flow"])
        debt = as_float(info.get("totalDebt")) or row(bal, ["Total Debt", "Net Debt"])
        cash = as_float(info.get("totalCash")) or row(bal, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"])
        equity = row(bal, ["Stockholders Equity", "Total Equity Gross Minority Interest", "Total Stockholder Equity"])
        gm = gp / revenue if revenue not in (None, 0) and gp is not None else None
        de = debt / equity if debt is not None and equity not in (None, 0) else None
        if de is None and as_float(info.get("debtToEquity")) is not None:
            raw = as_float(info.get("debtToEquity"))
            de = raw / 100 if raw and raw > 5 else raw
        market = {"last_price": round(price, 2) if price is not None else None, "previous_close": round(prev, 2) if prev is not None else None, "price_change_pct": pct(change), "market_cap": money(fast.get("market_cap") or info.get("marketCap"), cur), "enterprise_value": money(info.get("enterpriseValue"), cur), "trailing_pe": round(as_float(info.get("trailingPE")), 2) if as_float(info.get("trailingPE")) is not None else None, "forward_pe": round(as_float(info.get("forwardPE")), 2) if as_float(info.get("forwardPE")) is not None else None}
        metrics = {"total_revenue": money(revenue, cur), "revenue_growth": pct(info.get("revenueGrowth")), "gross_profit": money(gp, cur), "gross_margin": pct(gm), "net_income": money(ni, cur), "operating_cash_flow": money(ocf, cur), "free_cash_flow": money(fcf, cur), "total_debt": money(debt, cur), "total_cash": money(cash, cur), "stockholder_equity": money(equity, cur), "debt_to_equity": round(de, 2) if de is not None else None}
        has_data = any(v is not None for v in market.values()) or any(v is not None for v in metrics.values())
        return {"ticker": ticker, "company_name": info.get("longName") or info.get("shortName") or ticker, "currency": cur, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "data_status": "latest_available" if has_data else "unavailable", "source": "yfinance/Yahoo Finance via backend", "market_data": market, "financial_metrics": metrics, "note": "Yahoo Finance/yfinance data. Market prices may be delayed and statements may be latest available trailing or annual values."}
    except Exception as e:
        return {"ticker": ticker, "data_status": "unavailable", "error": str(e)}

def build_prompt(q: str, ticker: Optional[str], data: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    if data:
        user = f"User request: {q}\nResolved ticker: {ticker}\nBackend data: {data}\nUse only this backend data. If data_status is unavailable, explain that the company name or Yahoo Finance ticker may need correction."
    else:
        user = q
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]

async def generate_response(q: str, ticker: Optional[str] = None, mode: str = "chat") -> Dict[str, Any]:
    quick = fast_casual_reply(q)
    if quick:
        return {"mode": mode, "query": q, "ticker": None, "used_live_data": False, "facts": None, "qwen_status": "skipped_fast_reply", "answer": quick, "message": quick}
    resolved = resolve_ticker(q, ticker)
    data = fetch_financial_data(resolved) if wants_data(q, resolved) and resolved else None
    if not qwen_is_configured():
        return {"mode": mode, "query": q, "ticker": resolved, "used_live_data": bool(data), "facts": data, "qwen_status": "not_configured", "answer": "Hi, I am QFin Terminal. I can chat normally and specialize in finance. Qwen is not configured yet."}
    try:
        response = await call_qwen(build_prompt(q, resolved, data))
        content = clean_text(response["choices"][0]["message"]["content"])
        return {"mode": mode, "query": q, "ticker": resolved, "used_live_data": bool(data), "facts": data, "qwen_status": "success", "ai_report": {"content": content, "raw_model": response.get("model"), "usage": response.get("usage")}, "answer": content, "message": content}
    except (QwenClientError, KeyError, IndexError) as e:
        return {"mode": mode, "query": q, "ticker": resolved, "used_live_data": bool(data), "facts": data, "qwen_status": "error", "error": str(e), "answer": "The backend is connected, but the Qwen call failed. Check DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, and DASHSCOPE_MODEL in Render."}

@app.get("/")
def root(request: Request):
    base = str(request.base_url).rstrip("/")
    return {"app": "QFin Terminal API", "status": "running", "docs": f"{base}/docs", "health": f"{base}/health", "chat": f"{base}/chat", "examples": [f"{base}/market-data/TSLA", f"{base}/market-data/BBCA.JK", f"{base}/ticker/search?query=Honda"]}

@app.get("/health")
def health():
    return {"status": "ok", "service": "qfin-terminal-api", "version": "qfin-fast-chat-1.1", "qwen_configured": qwen_is_configured()}

@app.post("/analyze")
async def analyze(payload: AnalyzeRequest):
    return await generate_response(payload.query, payload.ticker, payload.mode)

@app.post("/chat")
async def chat(payload: ChatRequest):
    query = extract_chat_query(payload)
    result = await generate_response(query, payload.ticker, payload.mode or "chat")
    return {"id": "qfin-chat-response", "role": "assistant", "content": result.get("answer"), "answer": result.get("answer"), "data": result}

@app.post("/chat/stream")
async def chat_stream(payload: ChatRequest):
    async def text_generator():
        result = await chat(payload)
        yield result.get("content") or "No response generated."
    return StreamingResponse(text_generator(), media_type="text/plain; charset=utf-8")

@app.post("/chat/upload")
async def chat_upload(file: UploadFile = File(...)):
    return await upload_statement(file)

@app.get("/ticker/resolve")
def resolve_ticker_route(symbol: Optional[str] = None, query: Optional[str] = None):
    raw = symbol or query or ""
    resolved = resolve_ticker(raw, symbol)
    return {"symbol": resolved, "ticker": resolved, "status": "resolved" if resolved else "not_found"}

@app.get("/ticker/search")
def ticker_search_route(query: str):
    resolved = yahoo_symbol_search(query)
    return {"query": query, "ticker": resolved, "status": "resolved" if resolved else "not_found"}

@app.get("/market-data/{ticker}")
def market_data_route(ticker: str):
    return fetch_financial_data(ticker.strip().upper())

@app.post("/upload")
async def upload_statement(file: UploadFile = File(...)):
    return {"filename": file.filename, "status": "received", "next_step": "Parse CSV or Excel, normalize financial statement rows, then call /analyze."}
