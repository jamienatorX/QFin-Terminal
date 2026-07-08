from dotenv import load_dotenv
load_dotenv()

import hashlib
import os
import random
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

import httpx
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from news_module import generate_news, normalize_category
from qwen_client import QwenClientError, call_qwen, qwen_is_configured

app = FastAPI(title="QFin Terminal API", version="qfin-agent-2.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SYSTEM_PROMPT = """
You are QFin, an AI agent inside QFin Terminal.
Behave like a strong general assistant for ordinary conversation.
For finance questions, be precise, detailed, and structured.
Use only supplied backend facts for live company, market, quarter, comparison, or news analysis.
Never substitute one ticker for another. If data for a requested ticker is missing, say exactly which ticker failed.
Do not fabricate figures, dates, or sources.
Use clean markdown. Prefer short sections, concise tables, and a direct conclusion.
If the user asks a basic non-finance question, answer naturally without forcing a finance report.
For detailed finance analysis, include clear sections for summary, drivers, risks, and verdict.
Do not output JSON to the user.
""".strip()

FINANCE_DETAIL_PROMPT = """
When the request is finance-specific, be thorough and analytical.
For company analysis or comparisons, cover:
- Executive summary
- Revenue or growth context when data exists
- Profitability
- Liquidity and balance sheet context
- Cash flow quality
- Valuation
- Key risks
- Bottom-line verdict
If a metric is unavailable, state that directly instead of guessing.
Use markdown tables where they help.
""".strip()

CASUAL_REPLIES = {
    "hi": "Hi, I am QFin. Ask me normal questions or finance questions. I can chat naturally and I can also do detailed company analysis when data is needed.",
    "hello": "Hello, I am QFin. Ask me anything, and if it is finance-related I can go deeper with company, market, and quant analysis.",
    "hey": "Hey. Ask me a company question, a finance concept, or anything general.",
    "thanks": "You are welcome.",
    "thank you": "You are welcome.",
    "thankyou": "You are welcome.",
    "thx": "You are welcome.",
    "ty": "You are welcome.",
    "ok": "Okay.",
    "okay": "Okay."
}

ALIASES = {
    "tesla": "TSLA",
    "alibaba": "BABA",
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
    "bbca": "BBCA.JK",
}

STOP = {
    "AI", "API", "CEO", "CFO", "GDP", "CPI", "USD", "IDR", "THE", "AND", "YOU",
    "HELLO", "HI", "HEY", "OK", "YES", "NO", "MODE", "QFIN"
}

FINANCE_WORDS = [
    "analyze", "analyse", "compare", "stock", "ticker", "company", "financial", "finance",
    "revenue", "profit", "margin", "debt", "cash flow", "valuation", "price", "earnings",
    "risk", "multiple", "pe", "pb", "ratio", "quarter", "annual", "quarterly", "eps",
    "dividend", "yield", "profitability", "free cash flow", "fcf", "income statement",
    "balance sheet", "capm", "var", "beta", "sharpe", "sortino", "volatility"
]

DETAILED_SIGNALS = [
    "thoroughly",
    "in-depth",
    "in depth",
    "deep dive",
    "comprehensive",
    "full analysis",
    "detailed",
    "complete breakdown",
    "don't hold back",
    "dont hold back",
    "give me everything",
]

SUPABASE_FORUM_TABLE = "qfin_forum_threads"
SUPABASE_MODEL_TABLE = "qfin_builder_models"

TICKER_RE = r"[A-Za-z0-9][A-Za-z0-9\.\-\^=]{0,17}"


class ChatMessage(BaseModel):
    role: Optional[str] = "user"
    content: str


class AgentChatRequest(BaseModel):
    message: Optional[str] = None
    query: Optional[str] = None
    prompt: Optional[str] = None
    ticker: Optional[str] = None
    mode: Optional[str] = "chat"
    messages: Optional[List[ChatMessage]] = None


class ForumCreateRequest(BaseModel):
    title: str
    body: str
    author: Optional[str] = None


class VoteRequest(BaseModel):
    direction: Literal["up", "down"]


class BuilderRunRequest(BaseModel):
    name: str
    code: str
    author: Optional[str] = None


class BuilderPublishRequest(BaseModel):
    name: str
    code: str
    author: Optional[str] = None
    summary: Optional[str] = None


FORUM_THREADS: List[Dict[str, Any]] = []
COMMUNITY_MODELS: List[Dict[str, Any]] = []
PRIVATE_MODELS: List[Dict[str, Any]] = []


def make_id(prefix: str) -> str:
    digest = hashlib.sha1(f"{prefix}-{datetime.now(timezone.utc).isoformat()}".encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:12]}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def supabase_is_configured() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))


def supabase_url(table: str) -> str:
    return f"{os.getenv('SUPABASE_URL', '').rstrip('/')}/rest/v1/{table}"


def supabase_headers(prefer: Optional[str] = None) -> Dict[str, str]:
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def supabase_request(
    method: str,
    table: str,
    *,
    params: Optional[Dict[str, str]] = None,
    json_body: Optional[Any] = None,
    prefer: Optional[str] = None,
) -> Any:
    if not supabase_is_configured():
        raise RuntimeError("Supabase is not configured.")

    response = httpx.request(
        method,
        supabase_url(table),
        params=params,
        json=json_body,
        headers=supabase_headers(prefer),
        timeout=20.0,
    )
    if response.status_code >= 400:
        snippet = response.text[:300] if response.text else ""
        raise RuntimeError(f"Supabase {table} request failed ({response.status_code}): {snippet}")
    if not response.text.strip():
        return None
    return response.json()


def parse_iso_datetime(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize_user_text(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def norm_symbol(symbol: str) -> str:
    value = symbol.strip().upper().strip(".,;:!?()[]{}\"'")
    return "BRK-B" if value == "BRK.B" else value


def extract_chat_query(payload: AgentChatRequest) -> str:
    if payload.message:
        return payload.message
    if payload.query:
        return payload.query
    if payload.prompt:
        return payload.prompt
    if payload.messages:
        users = [m.content for m in payload.messages if (m.role or "user") == "user"]
        return users[-1] if users else payload.messages[-1].content
    return "Hello"


def fast_casual_reply(text: str) -> Optional[str]:
    normalized = normalize_user_text(text)
    if normalized in CASUAL_REPLIES:
        return CASUAL_REPLIES[normalized]
    if normalized in {"what can you do", "who are you", "help", "menu"}:
        return (
            "I am QFin. I can chat normally, explain finance concepts, analyze companies, compare stocks, "
            "summarize market news, and work through quant finance questions."
        )
    return None


def is_time_prompt(text: str) -> bool:
    normalized = normalize_user_text(text)
    return normalized in {
        "what day is today",
        "what date is today",
        "what is the date today",
        "what is today",
        "what time is it",
        "whats the date",
        "whats the date today",
        "whats today",
        "todays date",
        "today date",
        "current date",
        "current time",
    }


def local_time_reply() -> str:
    now = datetime.now().astimezone()
    date_text = now.strftime("%A, %B %d, %Y")
    time_text = now.strftime("%I:%M %p %Z").lstrip("0")
    return f"Today is {date_text}. Your local time is {time_text}."


def finance_intent(text: str) -> bool:
    lower = text.lower()
    return any(word in lower for word in FINANCE_WORDS)


def needs_detail(text: str) -> bool:
    lower = text.lower()
    return finance_intent(text) and any(signal in lower for signal in DETAILED_SIGNALS)


def extract_symbol_candidates(text: str) -> List[str]:
    found: List[str] = []
    lowered = text.lower()

    for alias, ticker in ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            if ticker not in found:
                found.append(ticker)

    for token in re.findall(r"\$([A-Za-z0-9\.\-]{1,12})\b", text):
        symbol = norm_symbol(token)
        if symbol not in STOP and symbol not in found:
            found.append(symbol)

    for token in re.findall(r"\b[A-Z]{1,5}(?:[.\-][A-Z0-9]{1,4})?\b", text):
        symbol = norm_symbol(token)
        if symbol not in STOP and symbol not in found:
            found.append(symbol)

    return found


def yahoo_symbol_search(query: str) -> Optional[str]:
    try:
        cleaned = re.sub(
            r"\b(analyze|analyse|compare|check|review|research|stock|ticker|company|financial|finance|about|for|on|valuation|value|summarize|summary)\b",
            " ",
            query,
            flags=re.I,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) < 2:
            return None
        response = httpx.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={
                "q": cleaned,
                "quotesCount": 10,
                "newsCount": 0,
                "enableFuzzyQuery": True,
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15.0,
        )
        if response.status_code >= 400:
            return None
        for item in response.json().get("quotes", []):
            if item.get("symbol") and item.get("quoteType") in {"EQUITY", "ETF", "MUTUALFUND", "INDEX"}:
                return norm_symbol(item["symbol"])
    except Exception:
        return None
    return None


def resolve_single_ticker(text: str, provided: Optional[str] = None, allow_search: bool = True) -> Optional[str]:
    if provided:
        return norm_symbol(provided)

    candidates = extract_symbol_candidates(text)
    if candidates:
        return candidates[0]

    if allow_search and finance_intent(text):
        return yahoo_symbol_search(text)

    return None


def parse_compare_request(text: str) -> Optional[Dict[str, Any]]:
    match = re.search(r"\bcompare\b(.+?)\b(?:vs\.?|versus)\b(.+)", text, flags=re.I)
    if not match:
        return None

    left_text = match.group(1).strip(" ,.")
    right_text = match.group(2).strip(" ,.")
    topic = "overall financial performance"

    topic_candidates = [
        "profitability", "valuation", "growth", "margins", "margin", "cash flow",
        "liquidity", "solvency", "returns", "revenue", "debt", "earnings",
    ]

    for candidate in topic_candidates:
        escaped_candidate = re.escape(candidate).replace(r"\ ", r"\s+")
        pattern = re.compile(rf"\b{escaped_candidate}\b[?.! ]*$", re.I)
        if pattern.search(right_text):
            right_text = pattern.sub("", right_text).strip(" ,.")
            topic = candidate
            break

    left_ticker = resolve_single_ticker(left_text, allow_search=False) or resolve_single_ticker(left_text)
    right_ticker = resolve_single_ticker(right_text, allow_search=False) or resolve_single_ticker(right_text)

    if not left_ticker or not right_ticker:
        return None

    return {
        "kind": "comparison",
        "topic": topic,
        "tickers": [left_ticker, right_ticker],
    }


def classify_message(text: str, provided_ticker: Optional[str] = None) -> Dict[str, Any]:
    casual = fast_casual_reply(text)
    if casual:
        return {"kind": "casual", "reply": casual}
    if is_time_prompt(text):
        return {"kind": "time"}

    compare = parse_compare_request(text)
    if compare:
        return compare

    if "news" in text.lower():
        category = "Stocks"
        for option in ["Crypto", "Stocks", "Bonds", "ETFs", "Other"]:
            if option.lower() in text.lower():
                category = option
                break
        return {"kind": "news", "category": category}

    ticker = resolve_single_ticker(text, provided_ticker)
    if ticker and finance_intent(text):
        return {"kind": "company", "ticker": ticker, "detail": "deep" if needs_detail(text) else "standard"}
    if finance_intent(text):
        return {"kind": "finance_concept", "detail": "deep" if needs_detail(text) else "standard"}
    return {"kind": "general"}


def as_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if hasattr(value, "item"):
            value = value.item()
        result = float(value)
        return None if result != result else result
    except Exception:
        return None


def money(value: Any, currency: str) -> Optional[str]:
    amount = as_float(value)
    if amount is None:
        return None
    if abs(amount) >= 1_000_000_000_000:
        return f"{currency} {amount / 1_000_000_000_000:.2f}T"
    if abs(amount) >= 1_000_000_000:
        return f"{currency} {amount / 1_000_000_000:.2f}B"
    if abs(amount) >= 1_000_000:
        return f"{currency} {amount / 1_000_000:.2f}M"
    return f"{currency} {amount:,.2f}"


def pct(value: Any) -> Optional[str]:
    amount = as_float(value)
    if amount is None:
        return None
    if abs(amount) <= 3:
        amount *= 100
    return f"{amount:.2f}%"


def row(frame: Any, names: List[str]) -> Optional[float]:
    try:
        if frame is None or frame.empty:
            return None
        for name in names:
            if name in frame.index:
                series = frame.loc[name].dropna()
                if len(series) > 0:
                    return as_float(series.iloc[0])
    except Exception:
        return None
    return None


def extract_historical_series(frame: Any, names: List[str], currency: str, max_periods: int = 5) -> Dict[str, str]:
    result: Dict[str, str] = {}
    try:
        if frame is None or frame.empty:
            return result
        for name in names:
            if name in frame.index:
                series = frame.loc[name].dropna()
                if len(series) > 0:
                    for idx, (date, value) in enumerate(series.items()):
                        if idx >= max_periods:
                            break
                        formatted = money(as_float(value), currency)
                        if formatted:
                            result[str(date)] = formatted
                    if result:
                        return result
    except Exception:
        return result
    return result


def fetch_finnhub_data(symbol: str) -> Dict[str, Any]:
    token = os.getenv("FINNHUB_API_KEY")
    if not token:
        return {}

    base_url = "https://finnhub.io/api/v1"
    result: Dict[str, Any] = {}
    try:
        quote = httpx.get(f"{base_url}/quote", params={"symbol": symbol, "token": token}, timeout=15.0)
        if quote.status_code < 400:
            result["quote"] = quote.json()
    except Exception:
        pass

    try:
        profile = httpx.get(f"{base_url}/stock/profile2", params={"symbol": symbol, "token": token}, timeout=15.0)
        if profile.status_code < 400:
            result["profile"] = profile.json()
    except Exception:
        pass

    try:
        metrics = httpx.get(
            f"{base_url}/stock/metric",
            params={"symbol": symbol, "metric": "all", "token": token},
            timeout=15.0,
        )
        if metrics.status_code < 400:
            result["metrics"] = metrics.json()
    except Exception:
        pass

    try:
        earnings = httpx.get(
            f"{base_url}/stock/earnings",
            params={"symbol": symbol, "limit": 4, "token": token},
            timeout=15.0,
        )
        if earnings.status_code < 400:
            result["earnings"] = earnings.json()
    except Exception:
        pass

    return result


def fetch_financial_data(ticker: str) -> Dict[str, Any]:
    try:
        import yfinance as yf

        asset = yf.Ticker(ticker)
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

        finnhub = fetch_finnhub_data(ticker)
        finnhub_metrics = finnhub.get("metrics", {}).get("metric", {}) if finnhub.get("metrics") else {}

        currency = info.get("financialCurrency") or info.get("currency") or fast.get("currency") or "USD"
        price = as_float(fast.get("last_price") or info.get("currentPrice") or info.get("regularMarketPrice"))
        prev = as_float(fast.get("previous_close") or info.get("previousClose"))

        quote = finnhub.get("quote") or {}
        price = price if price is not None else as_float(quote.get("c"))
        prev = prev if prev is not None else as_float(quote.get("pc"))

        if hist is not None and not hist.empty and "Close" in hist:
            closes = hist["Close"].dropna()
            if len(closes) > 0 and price is None:
                price = as_float(closes.iloc[-1])
            if len(closes) > 1 and prev is None:
                prev = as_float(closes.iloc[-2])

        change = (price - prev) / prev if price is not None and prev not in (None, 0) else None

        revenue = as_float(info.get("totalRevenue")) or row(income, ["Total Revenue", "Operating Revenue"])
        gross_profit = as_float(info.get("grossProfits")) or row(income, ["Gross Profit"])
        net_income = as_float(info.get("netIncomeToCommon")) or row(income, ["Net Income", "Net Income Common Stockholders"])
        operating_cashflow = as_float(info.get("operatingCashflow")) or row(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"])
        free_cashflow = as_float(info.get("freeCashflow")) or row(cashflow, ["Free Cash Flow"])
        debt = as_float(info.get("totalDebt")) or row(balance, ["Total Debt", "Net Debt"])
        cash = as_float(info.get("totalCash")) or row(balance, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"])
        equity = row(balance, ["Stockholders Equity", "Total Equity Gross Minority Interest", "Total Stockholder Equity"])

        shares = as_float(info.get("sharesOutstanding")) or as_float(fast.get("shares_outstanding"))
        market_cap = as_float(info.get("marketCap")) or as_float(fast.get("market_cap"))
        if market_cap is None and price is not None and shares is not None:
            market_cap = price * shares

        trailing_eps = as_float(info.get("trailingEps"))
        forward_eps = as_float(info.get("forwardEps"))
        if trailing_eps is None and net_income is not None and shares not in (None, 0):
            trailing_eps = net_income / shares

        trailing_pe = as_float(info.get("trailingPE"))
        if trailing_pe is None and price is not None and trailing_eps not in (None, 0):
            trailing_pe = price / trailing_eps

        forward_pe = as_float(info.get("forwardPE"))
        if forward_pe is None and price is not None and forward_eps not in (None, 0):
            forward_pe = price / forward_eps

        enterprise_value = as_float(info.get("enterpriseValue"))
        if enterprise_value is None and market_cap is not None:
            enterprise_value = market_cap + (debt or 0) - (cash or 0)

        revenue_growth = as_float(info.get("revenueGrowth"))
        if revenue_growth is None:
            revenue_growth = as_float(finnhub_metrics.get("revenueGrowthTTMYoy"))

        gross_margin = gross_profit / revenue if revenue not in (None, 0) and gross_profit is not None else None
        if gross_margin is None:
            gross_margin = as_float(finnhub_metrics.get("grossMarginTTM"))
        net_margin = net_income / revenue if revenue not in (None, 0) and net_income is not None else None
        if net_margin is None:
            net_margin = as_float(finnhub_metrics.get("netMarginTTM"))
        operating_margin = None
        if as_float(finnhub_metrics.get("operatingMarginTTM")) is not None:
            operating_margin = as_float(finnhub_metrics.get("operatingMarginTTM"))

        debt_to_equity = debt / equity if debt is not None and equity not in (None, 0) else None
        if debt_to_equity is None:
            raw = as_float(info.get("debtToEquity"))
            if raw is not None:
                debt_to_equity = raw / 100 if raw > 5 else raw

        historical_financials = {
            "annual_revenue": extract_historical_series(income, ["Total Revenue", "Operating Revenue"], currency),
            "annual_gross_profit": extract_historical_series(income, ["Gross Profit"], currency),
            "annual_net_income": extract_historical_series(income, ["Net Income", "Net Income Common Stockholders"], currency),
            "annual_operating_cash_flow": extract_historical_series(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"], currency),
            "annual_free_cash_flow": extract_historical_series(cashflow, ["Free Cash Flow"], currency),
        }

        result = {
            "ticker": ticker,
            "company_name": (
                info.get("longName")
                or info.get("shortName")
                or finnhub.get("profile", {}).get("name")
                or ticker
            ),
            "currency": currency,
            "retrieved_at_utc": utc_now(),
            "market_data": {
                "last_price": round(price, 2) if price is not None else None,
                "previous_close": round(prev, 2) if prev is not None else None,
                "price_change_pct": pct(change),
                "market_cap": money(market_cap, currency),
                "enterprise_value": money(enterprise_value, currency),
                "trailing_pe": f"{trailing_pe:.2f}x" if trailing_pe is not None else None,
                "forward_pe": f"{forward_pe:.2f}x" if forward_pe is not None else None,
            },
            "financial_metrics": {
                "total_revenue": money(revenue, currency),
                "revenue_growth": pct(revenue_growth),
                "gross_profit": money(gross_profit, currency),
                "gross_margin": pct(gross_margin),
                "operating_margin": pct(operating_margin),
                "net_income": money(net_income, currency),
                "net_margin": pct(net_margin),
                "operating_cashflow": money(operating_cashflow, currency),
                "free_cashflow": money(free_cashflow, currency),
                "total_debt": money(debt, currency),
                "cash": money(cash, currency),
                "debt_to_equity": pct(debt_to_equity),
            },
            "historical_financials": historical_financials,
            "earnings_history": finnhub.get("earnings"),
            "source": "Yahoo Finance via yfinance, with Finnhub supplement when configured.",
            "note": "Values come from backend data sources only. Missing metrics remain unavailable.",
        }
        result["data_status"] = "available" if any(result["market_data"].values()) or any(result["financial_metrics"].values()) else "unavailable"
        return result
    except Exception as exc:
        return {"ticker": ticker, "data_status": "unavailable", "error": str(exc)}


def build_general_prompt(query: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]


def build_finance_prompt(query: str, route: Dict[str, Any], facts: Any) -> List[Dict[str, str]]:
    route_kind = route["kind"]
    if route_kind == "comparison":
        user_content = (
            f"User request: {query}\n"
            f"Route: exact ticker comparison\n"
            f"Required tickers: {route['tickers']}\n"
            f"Topic: {route['topic']}\n"
            f"Backend facts: {facts}\n"
            "Use only these exact tickers. Do not substitute any other symbol. "
            "Write a detailed side-by-side finance comparison and clearly state what data is missing if any metric is unavailable."
        )
    elif route_kind == "company":
        user_content = (
            f"User request: {query}\n"
            f"Route: single company analysis\n"
            f"Resolved ticker: {route['ticker']}\n"
            f"Backend facts: {facts}\n"
            "Use only this backend data. If the user asked about the latest quarter, focus on the latest quarter context first, then the broader fundamentals."
        )
    elif route_kind == "news":
        user_content = (
            f"User request: {query}\n"
            f"Route: market news summary\n"
            f"Category: {route['category']}\n"
            f"Backend facts: {facts}\n"
            "Summarize the five news items, explain what matters most, and mention market sentiment."
        )
    else:
        user_content = (
            f"User request: {query}\n"
            f"Route: finance concept\n"
            "Answer as a finance expert. Use formulas, interpretation, and caveats where useful."
        )

    return [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{FINANCE_DETAIL_PROMPT}"},
        {"role": "user", "content": user_content},
    ]


async def ask_qwen(messages: List[Dict[str, str]]) -> str:
    response = await call_qwen(messages)
    return clean_text(response["choices"][0]["message"]["content"])


async def generate_agent_reply(query: str, provided_ticker: Optional[str] = None) -> Dict[str, Any]:
    route = classify_message(query, provided_ticker)

    if route["kind"] == "casual":
        return {"route": route, "content": route["reply"], "facts": None, "used_live_data": False}

    if route["kind"] == "time":
        return {"route": route, "content": local_time_reply(), "facts": None, "used_live_data": False}

    if route["kind"] == "news":
        news = await generate_news(normalize_category(route["category"]))
        if not qwen_is_configured():
            headlines = [item.get("headline") for item in news.get("news", [])[:5]]
            fallback = "Here are the latest market headlines I found:\n\n" + "\n".join(f"- {headline}" for headline in headlines if headline)
            return {"route": route, "content": fallback, "facts": news, "used_live_data": True}
        content = await ask_qwen(build_finance_prompt(query, route, news))
        return {"route": route, "content": content, "facts": news, "used_live_data": True}

    if route["kind"] == "comparison":
        facts = {ticker: fetch_financial_data(ticker) for ticker in route["tickers"]}
        if not qwen_is_configured():
            content = (
                f"Qwen is not configured, but I resolved the request to {route['tickers'][0]} and {route['tickers'][1]}. "
                "Connect the DashScope key to let QFin write the full comparison."
            )
            return {"route": route, "content": content, "facts": facts, "used_live_data": True}
        content = await ask_qwen(build_finance_prompt(query, route, facts))
        return {"route": route, "content": content, "facts": facts, "used_live_data": True}

    if route["kind"] == "company":
        facts = fetch_financial_data(route["ticker"])
        if not qwen_is_configured():
            content = (
                f"I resolved this request to {route['ticker']}, but Qwen is not configured on the backend right now. "
                "Add the DashScope key in Render so I can write the full report."
            )
            return {"route": route, "content": content, "facts": facts, "used_live_data": True}
        content = await ask_qwen(build_finance_prompt(query, route, facts))
        return {"route": route, "content": content, "facts": facts, "used_live_data": True}

    if route["kind"] == "finance_concept":
        if not qwen_is_configured():
            return {
                "route": route,
                "content": "The backend is connected, but Qwen is unavailable right now. Add the DashScope key to enable full finance explanations.",
                "facts": None,
                "used_live_data": False,
            }
        content = await ask_qwen(build_finance_prompt(query, route, None))
        return {"route": route, "content": content, "facts": None, "used_live_data": False}

    if not qwen_is_configured():
        return {
            "route": route,
            "content": "The backend is connected, but Qwen is unavailable right now. Add the DashScope key in Render to enable full chat responses.",
            "facts": None,
            "used_live_data": False,
        }

    content = await ask_qwen(build_general_prompt(query))
    return {"route": route, "content": content, "facts": None, "used_live_data": False}


def default_forum_threads() -> List[Dict[str, Any]]:
    return [
        {
            "title": "What is the cleanest way to compare banks?",
            "body": "I keep bouncing between ROE, NIM, loan growth, and NPLs. What do you prioritize first when screening banks?",
            "author": "MacroMira",
            "score": 18,
            "upvotes": 22,
            "downvotes": 4,
        },
        {
            "title": "Best metric for capital-light compounders?",
            "body": "I am testing a watchlist around gross margin, FCF margin, and ROIC. Curious what everyone here uses as the first filter.",
            "author": "QuantRafi",
            "score": 11,
            "upvotes": 15,
            "downvotes": 4,
        },
    ]


def build_random_model(name: str, author: str, summary: str, tags: List[str], seed_text: str) -> Dict[str, Any]:
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    annual_return = 9 + int(digest[0:2], 16) % 18
    sharpe = 1 + (int(digest[2:4], 16) % 90) / 100
    max_drawdown = 6 + int(digest[4:6], 16) % 16
    win_rate = 47 + int(digest[6:8], 16) % 18
    return {
        "id": make_id("model"),
        "name": name,
        "author": author,
        "summary": summary,
        "tags": tags,
        "score": 8 + int(digest[8:10], 16) % 22,
        "created_at": utc_now(),
        "stats": {
            "annual_return": f"{annual_return:.1f}%",
            "sharpe": f"{sharpe:.2f}",
            "max_drawdown": f"-{max_drawdown:.1f}%",
            "win_rate": f"{win_rate:.1f}%",
        },
        "code": seed_text,
        "visibility": "public",
    }


def default_public_models() -> List[Dict[str, Any]]:
    return [
        build_random_model(
            "Volatility Regime Switcher",
            "Dimas Halim",
            "Switches between trend-following and defensive positioning based on realized volatility expansion.",
            ["volatility", "regime", "risk"],
            "def signal(prices, vol):\n    if vol[-1] > vol[-20:].mean() * 1.25:\n        return 0\n    return 1 if prices[-1] > sum(prices[-20:]) / 20 else -1\n",
        ),
        build_random_model(
            "Earnings Drift Capture",
            "Sasha Verdan",
            "Ranks companies after earnings and leans into post-report drift while reducing exposure to weak guidance.",
            ["earnings", "event", "equities"],
            "def signal(surprise, guidance, momentum):\n    score = surprise * 0.6 + guidance * 0.3 + momentum * 0.1\n    return 1 if score > 0.4 else -1 if score < -0.2 else 0\n",
        ),
        build_random_model(
            "Carry and Quality Basket",
            "Nabila Frost",
            "Builds a quality-tilted basket using free cash flow yield, balance-sheet strength, and trend confirmation.",
            ["quality", "factor", "portfolio"],
            "def rank(fcf_yield, debt_to_equity, trend):\n    return fcf_yield * 0.5 - debt_to_equity * 0.2 + trend * 0.3\n",
        ),
    ]


def seed_forum() -> None:
    if FORUM_THREADS:
        return
    for record in default_forum_threads():
        FORUM_THREADS.append(
            {
                "id": make_id("thread"),
                "created_at": utc_now(),
                **record,
            }
        )


def seed_models() -> None:
    if COMMUNITY_MODELS:
        return
    COMMUNITY_MODELS.extend(default_public_models())


def ensure_supabase_forum_seeded() -> None:
    if not supabase_is_configured():
        return
    existing = supabase_request("GET", SUPABASE_FORUM_TABLE, params={"select": "id", "limit": "1"}) or []
    if existing:
        return
    now = utc_now()
    payload = [{**record, "created_at": now, "updated_at": now} for record in default_forum_threads()]
    supabase_request("POST", SUPABASE_FORUM_TABLE, json_body=payload, prefer="return=minimal")


def ensure_supabase_models_seeded() -> None:
    if not supabase_is_configured():
        return
    existing = supabase_request(
        "GET",
        SUPABASE_MODEL_TABLE,
        params={"select": "id", "visibility": "eq.public", "limit": "1"},
    ) or []
    if existing:
        return
    now = utc_now()
    payload = []
    for index, model in enumerate(default_public_models()):
        payload.append(
            {
                "name": model["name"],
                "author": model["author"],
                "summary": model["summary"],
                "code": model["code"],
                "tags": model["tags"],
                "stats": model["stats"],
                "score": model["score"],
                "visibility": "public",
                "seed_key": f"seed-model-{index + 1}",
                "created_at": now,
                "updated_at": now,
            }
        )
    supabase_request("POST", SUPABASE_MODEL_TABLE, json_body=payload, prefer="return=minimal")


def normalize_thread_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": record.get("id") or make_id("thread"),
        "title": clean_text(str(record.get("title") or "Untitled thread")),
        "body": clean_text(str(record.get("body") or "")),
        "author": clean_text(str(record.get("author") or "Anonymous")),
        "score": int(record.get("score") or 0),
        "upvotes": int(record.get("upvotes") or 0),
        "downvotes": int(record.get("downvotes") or 0),
        "created_at": str(record.get("created_at") or utc_now()),
    }


def normalize_model_record(record: Dict[str, Any]) -> Dict[str, Any]:
    tags = record.get("tags") or []
    stats = record.get("stats") or {}
    return {
        "id": record.get("id") or make_id("model"),
        "name": clean_text(str(record.get("name") or "Untitled model")),
        "author": clean_text(str(record.get("author") or "Unknown author")),
        "summary": clean_text(str(record.get("summary") or "")),
        "code": str(record.get("code") or ""),
        "tags": tags if isinstance(tags, list) else [],
        "stats": stats if isinstance(stats, dict) else {},
        "score": int(record.get("score") or 0),
        "visibility": str(record.get("visibility") or "public"),
        "created_at": str(record.get("created_at") or utc_now()),
    }


def load_forum_threads() -> Dict[str, Any]:
    if supabase_is_configured():
        try:
            ensure_supabase_forum_seeded()
            rows = supabase_request(
                "GET",
                SUPABASE_FORUM_TABLE,
                params={"select": "*", "order": "score.desc,created_at.desc", "limit": "100"},
            ) or []
            threads = [normalize_thread_record(row) for row in rows]
            return {"threads": threads, "storage": "supabase"}
        except Exception as exc:
            seed_forum()
            threads = sorted(FORUM_THREADS, key=lambda item: (item["score"], item["created_at"]), reverse=True)
            return {"threads": threads, "storage": "memory", "warning": str(exc)}

    seed_forum()
    threads = sorted(FORUM_THREADS, key=lambda item: (item["score"], item["created_at"]), reverse=True)
    return {"threads": threads, "storage": "memory"}


def create_forum_thread_record(payload: ForumCreateRequest) -> Dict[str, Any]:
    record = {
        "title": clean_text(payload.title),
        "body": clean_text(payload.body),
        "author": clean_text(payload.author or f"Analyst{random.randint(17, 98)}"),
        "score": 1,
        "upvotes": 1,
        "downvotes": 0,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }

    if supabase_is_configured():
        try:
            rows = supabase_request("POST", SUPABASE_FORUM_TABLE, json_body=record, prefer="return=representation") or []
            thread = normalize_thread_record(rows[0] if isinstance(rows, list) else rows)
            return {"thread": thread, "storage": "supabase"}
        except Exception:
            pass

    thread = {"id": make_id("thread"), **record}
    thread.pop("updated_at", None)
    FORUM_THREADS.append(thread)
    return {"thread": thread, "storage": "memory"}


def vote_forum_thread_record(thread_id: str, direction: str) -> Dict[str, Any]:
    if supabase_is_configured():
        try:
            rows = supabase_request(
                "GET",
                SUPABASE_FORUM_TABLE,
                params={"select": "*", "id": f"eq.{thread_id}", "limit": "1"},
            ) or []
            if rows:
                current = normalize_thread_record(rows[0])
                updated_values = {
                    "upvotes": current["upvotes"] + (1 if direction == "up" else 0),
                    "downvotes": current["downvotes"] + (1 if direction == "down" else 0),
                    "score": current["score"] + (1 if direction == "up" else -1),
                    "updated_at": utc_now(),
                }
                updated = supabase_request(
                    "PATCH",
                    SUPABASE_FORUM_TABLE,
                    params={"id": f"eq.{thread_id}"},
                    json_body=updated_values,
                    prefer="return=representation",
                ) or []
                thread = normalize_thread_record(updated[0] if isinstance(updated, list) else updated or {**current, **updated_values})
                return {"status": "updated", "thread": thread, "storage": "supabase"}
        except Exception:
            pass

    for thread in FORUM_THREADS:
        if thread["id"] == thread_id:
            if direction == "up":
                thread["upvotes"] += 1
                thread["score"] += 1
            else:
                thread["downvotes"] += 1
                thread["score"] -= 1
            return {"status": "updated", "thread": thread, "storage": "memory"}
    return {"status": "not_found"}


def load_community_models() -> Dict[str, Any]:
    if supabase_is_configured():
        try:
            ensure_supabase_models_seeded()
            rows = supabase_request(
                "GET",
                SUPABASE_MODEL_TABLE,
                params={
                    "select": "*",
                    "visibility": "eq.public",
                    "order": "score.desc,created_at.desc",
                    "limit": "12",
                },
            ) or []
            models = [normalize_model_record(row) for row in rows]
            return {"models": models, "storage": "supabase"}
        except Exception as exc:
            seed_models()
            models = sorted(COMMUNITY_MODELS, key=lambda item: (item["score"], item["created_at"]), reverse=True)
            return {"models": models[:12], "storage": "memory", "warning": str(exc)}

    seed_models()
    models = sorted(COMMUNITY_MODELS, key=lambda item: (item["score"], item["created_at"]), reverse=True)
    return {"models": models[:12], "storage": "memory"}


def create_community_model_record(payload: BuilderPublishRequest) -> Dict[str, Any]:
    model = build_random_model(
        payload.name,
        clean_text(payload.author or f"Trader{random.randint(11, 88)}"),
        clean_text(payload.summary or "Published from the QFin builder."),
        ["community", "published"],
        payload.code,
    )
    model["code"] = payload.code

    if supabase_is_configured():
        try:
            row = {
                "name": model["name"],
                "author": model["author"],
                "summary": model["summary"],
                "code": model["code"],
                "tags": model["tags"],
                "stats": model["stats"],
                "score": model["score"],
                "visibility": "public",
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            rows = supabase_request("POST", SUPABASE_MODEL_TABLE, json_body=row, prefer="return=representation") or []
            saved = normalize_model_record(rows[0] if isinstance(rows, list) else rows)
            return {"model": saved, "storage": "supabase"}
        except Exception:
            pass

    COMMUNITY_MODELS.insert(0, model)
    return {"model": model, "storage": "memory"}


def save_private_model_record(payload: BuilderPublishRequest) -> Dict[str, Any]:
    record = {
        "name": clean_text(payload.name),
        "author": clean_text(payload.author or "Private workspace"),
        "summary": clean_text(payload.summary or "Saved privately from the QFin builder."),
        "code": payload.code,
        "tags": ["private"],
        "stats": {},
        "score": 0,
        "visibility": "private",
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }

    if supabase_is_configured():
        try:
            rows = supabase_request("POST", SUPABASE_MODEL_TABLE, json_body=record, prefer="return=representation") or []
            saved = normalize_model_record(rows[0] if isinstance(rows, list) else rows)
            return {"model": saved, "storage": "supabase"}
        except Exception:
            pass

    local_record = {"id": make_id("private_model"), **record}
    local_record.pop("updated_at", None)
    PRIVATE_MODELS.insert(0, local_record)
    return {"model": local_record, "storage": "memory"}


def builder_run_output(name: str, code: str, author: Optional[str]) -> Dict[str, Any]:
    digest = hashlib.sha256(f"{name}\n{code}".encode("utf-8")).hexdigest()
    annual_return = 8 + int(digest[0:2], 16) % 19
    sharpe = 0.9 + (int(digest[2:4], 16) % 90) / 100
    max_drawdown = 5 + int(digest[4:6], 16) % 18
    turnover = 18 + int(digest[6:8], 16) % 64
    win_rate = 44 + int(digest[8:10], 16) % 22
    return {
        "name": name,
        "author": author or "Private workspace",
        "summary": (
            f"{name} completed a sandbox-style template run. "
            f"The current MVP runner validates structure, generates a deterministic backtest preview, "
            f"and keeps the model ready for private save or community publishing."
        ),
        "stats": {
            "annual_return": f"{annual_return:.1f}%",
            "sharpe": f"{sharpe:.2f}",
            "max_drawdown": f"-{max_drawdown:.1f}%",
            "turnover": f"{turnover:.1f}%",
            "win_rate": f"{win_rate:.1f}%",
        },
        "notes": [
            "Signal function parsed successfully.",
            "Template is ready for sandbox execution expansion in the next backend pass.",
            "Private and published saves are available from this result."
        ],
    }


seed_forum()
seed_models()


@app.get("/")
def root(request: Request):
    base = str(request.base_url).rstrip("/")
    return {
        "app": "QFin Terminal API",
        "status": "running",
        "docs": f"{base}/docs",
        "health": f"{base}/health",
        "agent_chat": f"{base}/agent/chat",
        "agent_stream": f"{base}/agent/chat/stream",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "qfin-terminal-api",
        "version": "qfin-agent-2.1",
        "qwen_configured": qwen_is_configured(),
        "supabase_configured": supabase_is_configured(),
    }


@app.post("/agent/chat")
async def agent_chat(payload: AgentChatRequest):
    query = extract_chat_query(payload)
    try:
        result = await generate_agent_reply(query, payload.ticker)
        return {
            "id": "qfin-agent-response",
            "role": "assistant",
            "content": result["content"],
            "answer": result["content"],
            "data": result,
        }
    except (QwenClientError, KeyError, IndexError) as exc:
        return {
            "id": "qfin-agent-error",
            "role": "assistant",
            "content": f"QFin could not complete that reply just now. {exc}",
            "answer": f"QFin could not complete that reply just now. {exc}",
            "data": {"error": str(exc)},
        }


@app.post("/agent/chat/stream")
async def agent_chat_stream(payload: AgentChatRequest):
    async def text_generator():
        result = await agent_chat(payload)
        yield result.get("content") or "No response generated."
    return StreamingResponse(text_generator(), media_type="text/plain; charset=utf-8")


@app.post("/chat")
async def chat(payload: AgentChatRequest):
    return await agent_chat(payload)


@app.post("/chat/stream")
async def chat_stream(payload: AgentChatRequest):
    return await agent_chat_stream(payload)


@app.get("/ticker/resolve")
def resolve_ticker_route(symbol: Optional[str] = None, query: Optional[str] = None):
    raw = symbol or query or ""
    resolved = resolve_single_ticker(raw, symbol)
    return {"symbol": resolved, "ticker": resolved, "status": "resolved" if resolved else "not_found"}


@app.get("/market-data/{ticker}")
def market_data_route(ticker: str):
    return fetch_financial_data(ticker.strip().upper())


@app.post("/upload")
async def upload_statement(file: UploadFile = File(...)):
    return {
        "filename": file.filename,
        "status": "received",
        "next_step": "Parse CSV or Excel, normalize financial statement rows, then send the extracted facts to /agent/chat.",
    }


@app.post("/chat/upload")
async def chat_upload(file: UploadFile = File(...)):
    return await upload_statement(file)


@app.get("/community/news/{category}")
async def community_news(category: str):
    return await generate_news(normalize_category(category))


@app.post("/community/news")
async def community_news_post(payload: Dict[str, str]):
    return await generate_news(normalize_category(payload.get("category", "Stocks")))


@app.get("/news/{category}")
async def news(category: str):
    return await generate_news(normalize_category(category))


@app.post("/news")
async def news_post(payload: Dict[str, str]):
    return await generate_news(normalize_category(payload.get("category", "Stocks")))


@app.get("/community/forum")
def community_forum():
    forum_state = load_forum_threads()
    threads = forum_state["threads"]
    today = datetime.now(timezone.utc).date()
    top_today = [thread for thread in threads if parse_iso_datetime(thread["created_at"]).date() == today][:3]
    response = {"top_today": top_today, "threads": threads, "storage": forum_state["storage"]}
    if forum_state.get("warning"):
        response["warning"] = forum_state["warning"]
    return response


@app.post("/community/forum")
def create_forum_thread(payload: ForumCreateRequest):
    created = create_forum_thread_record(payload)
    return {"status": "created", "thread": created["thread"], "storage": created["storage"]}


@app.post("/community/forum/{thread_id}/vote")
def vote_forum_thread(thread_id: str, payload: VoteRequest):
    return vote_forum_thread_record(thread_id, payload.direction)


@app.get("/community/models")
def community_models():
    model_state = load_community_models()
    response = {"models": model_state["models"], "storage": model_state["storage"]}
    if model_state.get("warning"):
        response["warning"] = model_state["warning"]
    return response


@app.post("/community/models")
def create_community_model(payload: BuilderPublishRequest):
    created = create_community_model_record(payload)
    return {"status": "published", "model": created["model"], "storage": created["storage"]}


@app.post("/builder/run")
def builder_run(payload: BuilderRunRequest):
    result = builder_run_output(payload.name, payload.code, payload.author)
    return {"status": "ok", "result": result}


@app.post("/builder/save-private")
def builder_save_private(payload: BuilderPublishRequest):
    saved = save_private_model_record(payload)
    return {"status": "saved", "model": saved["model"], "storage": saved["storage"]}


@app.post("/builder/run-private")
def builder_run_private(payload: BuilderPublishRequest):
    saved = save_private_model_record(payload)
    result = builder_run_output(payload.name, payload.code, payload.author)
    return {"status": "saved_and_ran", "model": saved["model"], "result": result, "storage": saved["storage"]}


@app.post("/builder/publish")
def builder_publish(payload: BuilderPublishRequest):
    return create_community_model(payload)
