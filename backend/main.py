from dotenv import load_dotenv
load_dotenv()

import re
from datetime import datetime, timezone
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from qwen_client import QwenClientError, call_qwen, qwen_is_configured

app = FastAPI(title="QFin Terminal API", version="global-finance-chat-1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

COMPANY_ALIASES = {
    "tesla": "TSLA",
    "tsla": "TSLA",
    "alibaba": "BABA",
    "baba": "BABA",
    "apple": "AAPL",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "amazon": "AMZN",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "meta": "META",
    "netflix": "NFLX",
    "uber": "UBER",
    "grab": "GRAB",
}

STOP_WORDS = {
    "AI", "API", "APP", "CEO", "CFO", "COO", "GDP", "CPI", "USD", "IDR", "AUD", "SGD", "EUR",
    "THE", "AND", "YOU", "ARE", "CAN", "HOW", "WHAT", "WHY", "PLEASE", "THANK", "THANKS",
    "HELLO", "HI", "HEY", "OK", "YES", "NO", "THIS", "THAT", "A", "AN", "TO", "FOR", "OF", "IN", "ON"
}

FINANCE_WORDS = [
    "analyze", "analyse", "analysis", "stock", "ticker", "company", "financial", "finance",
    "revenue", "profit", "margin", "debt", "cash flow", "valuation", "price", "earnings",
    "risk", "market cap", "fundamental", "ratio", "income statement", "balance sheet", "cashflow",
]

TICKER_PATTERN = r"[A-Za-z0-9][A-Za-z0-9\.\-\^=]{0,17}"

def extract_chat_query(payload: ChatRequest) -> str:
    if payload.message:
        return payload.message
    if payload.query:
        return payload.query
    if payload.prompt:
        return payload.prompt
    if payload.messages:
        user_messages = [m.content for m in payload.messages if (m.role or "user") == "user"]
        if user_messages:
            return user_messages[-1]
        return payload.messages[-1].content
    return "Hello"

def clean_frontend_text(text: str) -> str:
    cleaned = text.replace("**", "").replace("*", "").replace("#", "")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n[ \t]+", "\n", cleaned).strip()
    return cleaned

def normalize_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper().strip(".,;:!?()[]{}\"'")
    if symbol == "BRK.B":
        return "BRK-B"
    return symbol

def to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if hasattr(value, "item"):
            value = value.item()
        number = float(value)
        if number != number:
            return None
        return number
    except Exception:
        return None

def money(value: Any, currency: str = "USD") -> Optional[str]:
    number = to_float(value)
    if number is None:
        return None
    if abs(number) >= 1_000_000_000_000:
        return f"{currency} {number / 1_000_000_000_000:.2f}T"
    if abs(number) >= 1_000_000_000:
        return f"{currency} {number / 1_000_000_000:.2f}B"
    if abs(number) >= 1_000_000:
        return f"{currency} {number / 1_000_000:.2f}M"
    return f"{currency} {number:,.2f}"

def percent(value: Any) -> Optional[str]:
    number = to_float(value)
    if number is None:
        return None
    if abs(number) <= 3:
        number *= 100
    return f"{number:.2f}%"

def row_value(frame: Any, names: List[str]) -> Optional[float]:
    try:
        if frame is None or frame.empty:
            return None
        for name in names:
            if name in frame.index:
                series = frame.loc[name].dropna()
                if len(series) > 0:
                    return to_float(series.iloc[0])
    except Exception:
        return None
    return None

def has_finance_intent(query: str) -> bool:
    lower = query.lower()
    return any(word in lower for word in FINANCE_WORDS)

def yahoo_symbol_search(query: str) -> Optional[str]:
    try:
        import httpx

        search_text = re.sub(
            r"\b(analyze|analyse|check|review|stock|ticker|company|financial|finance|about|for|on)\b",
            " ",
            query,
            flags=re.I,
        )
        search_text = re.sub(r"\s+", " ", search_text).strip()

        if len(search_text) < 2:
            return None

        with httpx.Client(timeout=8, follow_redirects=True) as client:
            response = client.get(
                "https://query2.finance.yahoo.com/v1/finance/search",
                params={
                    "q": search_text,
                    "quotesCount": 8,
                    "newsCount": 0,
                    "enableFuzzyQuery": True,
                },
                headers={"User-Agent": "Mozilla/5.0"},
            )

        if response.status_code >= 400:
            return None

        quotes = response.json().get("quotes", [])
        allowed = {"EQUITY", "ETF", "MUTUALFUND", "INDEX"}

        for quote in quotes:
            symbol = quote.get("symbol")
            quote_type = quote.get("quoteType")
            if symbol and quote_type in allowed:
                return normalize_symbol(symbol)

    except Exception:
        return None

    return None

def resolve_ticker(query: str, provided: Optional[str] = None) -> Optional[str]:
    if provided:
        return normalize_symbol(provided)

    lower = query.lower()

    for name, ticker in COMPANY_ALIASES.items():
        if re.search(rf"\b{re.escape(name)}\b", lower):
            return ticker

    cashtag = re.search(rf"\$({TICKER_PATTERN})\b", query)
    if cashtag:
        candidate = normalize_symbol(cashtag.group(1))
        if candidate not in STOP_WORDS:
            return candidate

    after_word = re.search(
        rf"\b(?:analyze|analyse|check|review|research|about|stock|ticker|company|financials?|value|valuation)\s+({TICKER_PATTERN})\b",
        query,
        re.I,
    )
    if after_word:
        candidate = normalize_symbol(after_word.group(1))
        if candidate not in STOP_WORDS:
            return candidate

    global_tickers = re.findall(
        r"\b(?:[0-9]{1,6}|[A-Z]{1,6})(?:[\.\-][A-Z0-9]{1,6}){1,2}\b",
        query,
    )
    for token in global_tickers:
        candidate = normalize_symbol(token)
        if candidate not in STOP_WORDS:
            return candidate

    uppercase_tickers = re.findall(r"\b[A-Z]{1,5}(?:[\.-][A-Z])?\b", query)
    for token in uppercase_tickers:
        candidate = normalize_symbol(token)
        if candidate not in STOP_WORDS:
            return candidate

    if has_finance_intent(query):
        return yahoo_symbol_search(query)

    return None

def wants_finance_data(query: str, ticker: Optional[str]) -> bool:
    if not ticker:
        return False

    compact_query = re.sub(r"[^A-Za-z0-9\.\-\^=]", "", query).upper()

    if compact_query == ticker.upper():
        return True

    return has_finance_intent(query) or ticker.lower() in query.lower() or ticker.upper() in query.upper()

def fetch_financial_data(ticker: str) -> Dict[str, Any]:
    try:
        import yfinance as yf

        asset = yf.Ticker(ticker)

        info = {}
        fast = {}

        try:
            info = asset.get_info() or {}
        except Exception:
            info = {}

        try:
            fast = dict(asset.fast_info or {})
        except Exception:
            fast = {}

        try:
            hist = asset.history(period="5d", interval="1d", auto_adjust=False)
        except Exception:
            hist = None

        try:
            income = asset.financials
        except Exception:
            income = None

        try:
            balance = asset.balance_sheet
        except Exception:
            balance = None

        try:
            cashflow = asset.cashflow
        except Exception:
            cashflow = None

        currency = info.get("financialCurrency") or info.get("currency") or fast.get("currency") or "USD"

        price = to_float(fast.get("last_price") or info.get("currentPrice") or info.get("regularMarketPrice"))
        previous_close = to_float(fast.get("previous_close") or info.get("previousClose"))

        if hist is not None and not hist.empty and "Close" in hist:
            closes = hist["Close"].dropna()
            if len(closes) > 0 and price is None:
                price = to_float(closes.iloc[-1])
            if len(closes) > 1 and previous_close is None:
                previous_close = to_float(closes.iloc[-2])

        price_change = None
        if price is not None and previous_close not in (None, 0):
            price_change = (price - previous_close) / previous_close

        revenue = to_float(info.get("totalRevenue")) or row_value(income, ["Total Revenue", "Operating Revenue"])
        gross_profit = to_float(info.get("grossProfits")) or row_value(income, ["Gross Profit"])
        net_income = to_float(info.get("netIncomeToCommon")) or row_value(income, ["Net Income", "Net Income Common Stockholders"])
        operating_cash_flow = to_float(info.get("operatingCashflow")) or row_value(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"])
        free_cash_flow = to_float(info.get("freeCashflow")) or row_value(cashflow, ["Free Cash Flow"])
        debt = to_float(info.get("totalDebt")) or row_value(balance, ["Total Debt", "Net Debt"])
        cash = to_float(info.get("totalCash")) or row_value(balance, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"])
        equity = row_value(balance, ["Stockholders Equity", "Total Equity Gross Minority Interest", "Total Stockholder Equity"])

        gross_margin = gross_profit / revenue if revenue not in (None, 0) and gross_profit is not None else None
        debt_to_equity = debt / equity if debt is not None and equity not in (None, 0) else None

        if debt_to_equity is None and to_float(info.get("debtToEquity")) is not None:
            raw = to_float(info.get("debtToEquity"))
            debt_to_equity = raw / 100 if raw and raw > 5 else raw

        market_data = {
            "last_price": round(price, 2) if price is not None else None,
            "previous_close": round(previous_close, 2) if previous_close is not None else None,
            "price_change_pct": percent(price_change),
            "market_cap": money(fast.get("market_cap") or info.get("marketCap"), currency),
            "enterprise_value": money(info.get("enterpriseValue"), currency),
            "trailing_pe": round(to_float(info.get("trailingPE")), 2) if to_float(info.get("trailingPE")) is not None else None,
            "forward_pe": round(to_float(info.get("forwardPE")), 2) if to_float(info.get("forwardPE")) is not None else None,
            "fifty_two_week_high": round(to_float(info.get("fiftyTwoWeekHigh") or fast.get("year_high")), 2) if to_float(info.get("fiftyTwoWeekHigh") or fast.get("year_high")) is not None else None,
            "fifty_two_week_low": round(to_float(info.get("fiftyTwoWeekLow") or fast.get("year_low")), 2) if to_float(info.get("fiftyTwoWeekLow") or fast.get("year_low")) is not None else None,
        }

        financial_metrics = {
            "total_revenue": money(revenue, currency),
            "revenue_growth": percent(info.get("revenueGrowth")),
            "gross_profit": money(gross_profit, currency),
            "gross_margin": percent(gross_margin),
            "net_income": money(net_income, currency),
            "operating_cash_flow": money(operating_cash_flow, currency),
            "free_cash_flow": money(free_cash_flow, currency),
            "total_debt": money(debt, currency),
            "total_cash": money(cash, currency),
            "stockholder_equity": money(equity, currency),
            "debt_to_equity": round(debt_to_equity, 2) if debt_to_equity is not None else None,
        }

        has_data = any(v is not None for v in market_data.values()) or any(v is not None for v in financial_metrics.values())

        return {
            "ticker": ticker,
            "company_name": info.get("longName") or info.get("shortName") or ticker,
            "currency": currency,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "data_status": "latest_available" if has_data else "unavailable",
            "source": "yfinance/Yahoo Finance via backend",
            "market_data": market_data,
            "financial_metrics": financial_metrics,
            "note": "Supports any ticker recognized by Yahoo Finance/yfinance, including international suffixes like .HK, .JK, .T, .KS, .NS, .AX, .L, .PA, .DE and others. Market prices may be delayed and statements may be latest available trailing or annual values.",
        }

    except Exception as error:
        return {
            "ticker": ticker,
            "data_status": "unavailable",
            "error": str(error),
        }

def build_prompt(query: str, ticker: Optional[str], data: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    if data:
        system = (
            "You are QFin Terminal, an AI chat assistant specialized in finance. "
            "Analyze only the provided backend data. Do not invent missing numbers. "
            "Use plain text only, no markdown, no JSON. "
            "Structure the response as: Fact. Interpretation. Watch Items. Disclaimer."
        )

        user = (
            f"User request: {query}\n"
            f"Resolved ticker: {ticker}\n"
            f"Backend data: {data}\n"
            "Write a clear analyst-style response using the provided data. "
            "Mention that the data is latest available from the backend provider. "
            "If data_status is unavailable, tell the user the ticker may be unsupported or needs the correct Yahoo Finance ticker suffix."
        )

    else:
        system = (
            "You are QFin Terminal, a normal friendly AI chatbot specialized in finance. "
            "You can answer daily conversation normally, like greetings and general questions. "
            "When the user asks finance, accounting, economics, company, or stock questions, answer like a careful finance assistant. "
            "Use plain text only, no markdown, no JSON."
        )
        user = query

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

async def generate_response(query: str, ticker: Optional[str] = None, mode: str = "chat") -> Dict[str, Any]:
    resolved = resolve_ticker(query, ticker)
    live_data = fetch_financial_data(resolved) if wants_finance_data(query, resolved) and resolved else None
    messages = build_prompt(query, resolved, live_data)

    if not qwen_is_configured():
        fallback = (
            "Hi, I am QFin Terminal. I can chat normally and I specialize in finance. "
            "Qwen is not configured yet, so add DASHSCOPE_API_KEY in Render to enable full AI replies."
        )
        return {
            "mode": mode,
            "query": query,
            "ticker": resolved,
            "used_live_data": bool(live_data),
            "facts": live_data,
            "qwen_status": "not_configured",
            "answer": fallback,
        }

    try:
        qwen_response = await call_qwen(messages)
        content = clean_frontend_text(qwen_response["choices"][0]["message"]["content"])

        return {
            "mode": mode,
            "query": query,
            "ticker": resolved,
            "used_live_data": bool(live_data),
            "facts": live_data,
            "qwen_status": "success",
            "ai_report": {
                "content": content,
                "raw_model": qwen_response.get("model"),
                "usage": qwen_response.get("usage"),
            },
            "answer": content,
            "message": content,
        }

    except (QwenClientError, KeyError, IndexError) as error:
        fallback = (
            "The backend is connected, but the Qwen call failed. "
            "Check DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, and DASHSCOPE_MODEL in Render."
        )
        return {
            "mode": mode,
            "query": query,
            "ticker": resolved,
            "used_live_data": bool(live_data),
            "facts": live_data,
            "qwen_status": "error",
            "error": str(error),
            "answer": fallback,
        }

@app.get("/")
def root(request: Request):
    base_url = str(request.base_url).rstrip("/")
    return {
        "app": "QFin Terminal API",
        "status": "running",
        "docs": f"{base_url}/docs",
        "health": f"{base_url}/health",
        "chat": f"{base_url}/chat",
        "market_data_examples": [
            f"{base_url}/market-data/TSLA",
            f"{base_url}/market-data/9988.HK",
            f"{base_url}/market-data/BBCA.JK",
        ],
    }

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "qfin-terminal-api",
        "version": "global-finance-chat-1.0",
        "qwen_configured": qwen_is_configured(),
    }

@app.post("/analyze")
async def analyze(payload: AnalyzeRequest):
    return await generate_response(payload.query, payload.ticker, payload.mode)

@app.post("/chat")
async def chat(payload: ChatRequest):
    query = extract_chat_query(payload)
    result = await generate_response(query, payload.ticker, payload.mode or "chat")

    return {
        "id": "qfin-chat-response",
        "role": "assistant",
        "content": result.get("answer"),
        "answer": result.get("answer"),
        "data": result,
    }

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

    return {
        "symbol": resolved,
        "ticker": resolved,
        "status": "resolved" if resolved else "not_found",
    }

@app.get("/ticker/search")
def ticker_search_route(query: str):
    resolved = yahoo_symbol_search(query)

    return {
        "query": query,
        "ticker": resolved,
        "status": "resolved" if resolved else "not_found",
    }

@app.get("/market-data/{ticker}")
def market_data_route(ticker: str):
    return fetch_financial_data(ticker.strip().upper())

@app.post("/upload")
async def upload_statement(file: UploadFile = File(...)):
    return {
        "filename": file.filename,
        "status": "received",
        "next_step": "Parse CSV or Excel, normalize financial statement rows, then call /analyze.",
    }
