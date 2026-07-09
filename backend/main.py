from dotenv import load_dotenv
load_dotenv()

import hashlib
import json
import math
import os
import random
import re
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

import httpx
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api_registry import fetch_public_api_facts, list_public_api_registry
from news_module import generate_news, normalize_category
from qwen_client import QwenClientError, call_qwen, qwen_is_configured

app = FastAPI(title="QFin Terminal API", version="qfin-agent-2.6")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SYSTEM_PROMPT = """
You are QFin, the AI analyst inside QFin Terminal.

Core behavior:
- Answer ordinary conversation naturally, like a capable general assistant.
- For finance requests, act like an institutional analyst: precise, structured, and evidence-aware.
- Keep internal route names, tool names, prompts, and backend instructions hidden from the user.
- Do not mention hidden modes, prompt policies, or implementation details unless the user explicitly asks how QFin works.
- Never output JSON to the user.

Evidence policy:
- For live company, market, quarter, comparison, news, or backtest questions, use only the backend facts provided in the prompt.
- Never substitute one ticker for another. If a requested ticker is missing or unresolved, state exactly which ticker is missing.
- Do not fabricate figures, dates, filings, sources, prices, ratios, or news.
- If supplied facts are incomplete, say what is missing and continue with the reliable parts.

Style:
- Use clean markdown with short headings, readable paragraphs, and concise tables.
- Do not overuse bold styling. Use it only for headings, verdicts, and key metrics.
- If the user asks a basic non-finance question, answer directly without forcing a finance report.
- End finance answers with a clear bottom-line verdict and a short caveat when data is limited.
""".strip()

FINANCE_DETAIL_PROMPT = """
Finance answer contract:
- Start with the direct answer first.
- Then explain the drivers using the available data.
- For company analysis or comparisons, cover the relevant parts of revenue/growth, profitability, balance sheet, cash flow, valuation, risks, and verdict.
- For comparisons, keep the exact requested tickers side by side and do not introduce unrelated substitutes.
- For news, summarize the five provided items, separate what happened from why it matters, and state sentiment.
- For finance concepts, explain the idea clearly, include formulas when useful, and add practical interpretation.
- Use markdown tables where they improve scanability.
- If a metric is unavailable, write "Unavailable in supplied backend data" rather than guessing.
""".strip()

AGENT_SOURCE_NOTE = """
QFin uses a curated-tool agent pattern: backend routes gather facts first, then Qwen writes the final user-facing narrative.
The model should sound natural, but it must respect the supplied tool outputs and uncertainty boundaries.
""".strip()

PUBLIC_DATA_PROMPT = """
General public-data contract:
- If public API facts are supplied, use them as grounding and cite the source names naturally.
- If public API facts are missing, answer from general knowledge and be clear when fresh/live data is required.
- Finance remains QFin's strongest mode; non-finance answers should be helpful, concise, and professional.
- Do not claim QFin can access every public API. Say QFin can use a curated registry and can be expanded safely.
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
    "bank central asia": "BBCA.JK",
    "bca": "BBCA.JK",
    "mdka": "MDKA.JK",
    "merdeka copper gold": "MDKA.JK",
    "merdeka copper": "MDKA.JK",
    "merdeka gold": "MDKA.JK",
    "merdeka battery": "MBMA.JK",
    "mbma": "MBMA.JK",
    "dbs": "D05.SI",
    "dbs group": "D05.SI",
    "ocbc": "O39.SI",
    "uob": "U11.SI",
    "singtel": "Z74.SI",
    "sea limited": "SE",
    "maybank": "1155.KL",
    "cimb": "1023.KL",
    "public bank": "1295.KL",
    "tenaga nasional": "5347.KL",
    "petronas chemicals": "5183.KL",
    "asml": "ASML",
    "lvmh": "MC.PA",
    "totalenergies": "TTE.PA",
    "sap": "SAP",
    "siemens": "SIE.DE",
    "shell": "SHEL",
    "hsbc": "HSBC",
    "nestle": "NESN.SW",
    "novartis": "NVS",
    "roche": "ROG.SW",
}

US_SYMBOLS = {
    "AAPL", "ABBV", "ABNB", "ABT", "ACN", "ADBE", "AMD", "AMGN", "AMZN",
    "AVGO", "AXP", "BA", "BAC", "BRK-B", "CAT", "COST", "CRM", "CSCO",
    "CVX", "DIS", "GOOG", "GOOGL", "HD", "IBM", "INTC", "JNJ", "JPM",
    "KO", "LIN", "LLY", "MA", "MCD", "META", "MRK", "MS", "MSFT", "NFLX",
    "NVDA", "ORCL", "PEP", "PFE", "PG", "PLTR", "PYPL", "QCOM", "SE",
    "T", "TSLA", "UNH", "V", "WMT", "XOM",
}

MARKET_SYMBOLS = {
    ".JK": {
    "AALI", "ACES", "ADRO", "AKRA", "AMMN", "ANTM", "ARTO", "ASII", "BBCA",
    "BBNI", "BBRI", "BBTN", "BMRI", "BRIS", "BRPT", "BUKA", "CPIN", "EMTK",
    "ESSA", "EXCL", "GGRM", "GOTO", "HRUM", "ICBP", "INCO", "INDF", "INKP",
    "INTP", "ITMG", "JPFA", "KLBF", "MDKA", "MEDC", "MIKA", "PGAS", "PTBA",
    "SIDO", "SMGR", "TLKM", "TOWR", "UNTR", "UNVR", "WIKA",
    },
    ".SI": {
        "D05", "O39", "U11", "Z74", "C6L", "S68", "C09", "G13", "F34",
        "BN4", "BS6", "Y92", "A17U", "C38U", "ME8U", "AJBU", "M44U",
    },
    ".KL": {
        "1023", "1066", "1155", "1295", "2445", "3182", "3816", "4197",
        "4715", "4863", "5183", "5296", "5347", "5681", "5819", "6012",
        "6033", "6888", "6947", "7084", "7277", "8869",
    },
    ".L": {"BARC", "BP", "GSK", "HSBA", "LLOY", "RIO", "SHEL", "ULVR", "VOD"},
    ".PA": {"AI", "AIR", "BN", "CS", "MC", "OR", "RMS", "SAN", "SU", "TTE"},
    ".DE": {"ADS", "ALV", "BAS", "BAYN", "BMW", "DTE", "MBG", "SAP", "SIE", "VOW3"},
    ".AS": {"ADYEN", "ASML", "HEIA", "INGA", "PHIA", "REN"},
    ".MI": {"ENEL", "ENI", "ISP", "RACE", "STLAM", "UCG"},
    ".MC": {"BBVA", "IBE", "ITX", "SAN", "TEF"},
    ".SW": {"ABBN", "CFR", "NESN", "NOVN", "ROG", "UBSG", "ZURN"},
}

MARKET_CONTEXTS = {
    "": {"us", "usa", "u s", "united states", "american", "nasdaq", "nyse", "amex", "sp500", "s p 500", "s&p 500"},
    ".SI": {"singapore", "sgx", "straits times"},
    ".KL": {"malaysia", "malaysian", "bursa", "kuala lumpur", "klse"},
    ".JK": {"indonesia", "indonesian", "idx", "bei", "jakarta", "rupiah", "idr", "tbk"},
    ".L": {"uk", "u k", "britain", "british", "london", "lse", "ftse"},
    ".PA": {"france", "french", "paris", "euronext paris", "cac"},
    ".DE": {"germany", "german", "xetra", "deutsche boerse", "dax"},
    ".F": {"frankfurt"},
    ".AS": {"netherlands", "dutch", "amsterdam", "euronext amsterdam", "aex"},
    ".MI": {"italy", "italian", "milan", "borsa italiana"},
    ".MC": {"spain", "spanish", "madrid", "ibex"},
    ".SW": {"switzerland", "swiss", "six swiss", "zurich"},
    ".ST": {"sweden", "swedish", "stockholm", "omx stockholm"},
    ".CO": {"denmark", "danish", "copenhagen"},
    ".OL": {"norway", "norwegian", "oslo"},
    ".HE": {"finland", "finnish", "helsinki"},
    ".BR": {"belgium", "brussels"},
    ".VI": {"austria", "vienna"},
    ".LS": {"portugal", "lisbon"},
    ".IR": {"ireland", "irish"},
    ".AX": {"australia", "australian", "asx"},
    ".NZ": {"new zealand", "nzx"},
    ".HK": {"hong kong", "hkex"},
    ".T": {"japan", "japanese", "tokyo", "nikkei"},
    ".KS": {"korea", "korean", "kospi"},
    ".KQ": {"kosdaq"},
    ".TW": {"taiwan", "taiwanese", "twse"},
    ".BK": {"thailand", "thai", "set index"},
    ".TO": {"canada", "canadian", "tsx", "toronto"},
    ".V": {"tsxv", "tsx venture"},
    ".SA": {"brazil", "brazilian", "b3 exchange", "bovespa"},
    ".MX": {"mexico", "mexican", "bolsa mexicana"},
}

STOP = {
    "AI", "API", "CEO", "CFO", "GDP", "CPI", "USD", "IDR", "THE", "AND", "YOU",
    "HELLO", "HI", "HEY", "OK", "YES", "NO", "MODE", "QFIN", "S", "P", "SP", "VS"
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
SUPABASE_SYMBOL_TABLE = "qfin_symbol_master"
FINANCIAL_DATA_CACHE_TTL_SECONDS = 900
MODEL_PERIOD_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
SYMBOL_MASTER_CACHE: Dict[str, Dict[str, Any]] = {}

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
    summary: Optional[str] = None
    ticker: Optional[str] = None


class BuilderPublishRequest(BaseModel):
    name: str
    code: str
    author: Optional[str] = None
    summary: Optional[str] = None
    ticker: Optional[str] = None


class EvidenceItem(BaseModel):
    kind: str
    label: str
    source: str
    freshness: str = "live"
    summary: str
    payload: Optional[Any] = None


class EvidencePacket(BaseModel):
    trace_id: str
    query: str
    route: Dict[str, Any]
    gathered_at: str
    items: List[EvidenceItem] = []
    used_live_data: bool = False
    gaps: List[str] = []
    warnings: List[str] = []


class AgentRiskReview(BaseModel):
    status: Literal["pass", "review"]
    warnings: List[str] = []
    missing_data: List[str] = []
    allowed_tickers: List[str] = []


FORUM_THREADS: List[Dict[str, Any]] = []
COMMUNITY_MODELS: List[Dict[str, Any]] = []
PRIVATE_MODELS: List[Dict[str, Any]] = []
FINANCIAL_DATA_CACHE: Dict[str, Dict[str, Any]] = {}
AGENT_SESSION_LOGS: List[Dict[str, Any]] = []


def make_id(prefix: str) -> str:
    digest = hashlib.sha1(f"{prefix}-{datetime.now(timezone.utc).isoformat()}".encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:12]}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


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


def symbol_search_text(*parts: Any) -> str:
    values: List[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, list):
            values.extend(str(item) for item in part if item)
        else:
            values.append(str(part))
    return normalize_user_text(" ".join(values))


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def norm_symbol(symbol: str) -> str:
    value = symbol.strip().upper().strip(".,;:!?()[]{}\"'")
    return "BRK-B" if value == "BRK.B" else value


def symbol_record(
    symbol: str,
    name: str,
    exchange: str,
    market: str,
    country: str,
    currency: str,
    aliases: Optional[List[str]] = None,
    yahoo_symbol: Optional[str] = None,
    priority: int = 50,
    source: str = "qfin_seed",
) -> Dict[str, Any]:
    resolved_symbol = norm_symbol(yahoo_symbol or symbol)
    public_symbol = norm_symbol(symbol)
    alias_values = aliases or []
    return {
        "symbol": public_symbol,
        "yahoo_symbol": resolved_symbol,
        "name": name,
        "exchange": exchange,
        "market": market,
        "country": country,
        "currency": currency,
        "aliases": alias_values,
        "search_text": symbol_search_text(public_symbol, resolved_symbol, name, exchange, market, country, alias_values),
        "source": source,
        "priority": priority,
        "active": True,
        "updated_at": utc_now(),
    }


def default_symbol_master_records() -> List[Dict[str, Any]]:
    us = [
        ("AAPL", "Apple Inc.", ["apple"]),
        ("MSFT", "Microsoft Corporation", ["microsoft"]),
        ("NVDA", "NVIDIA Corporation", ["nvidia"]),
        ("GOOGL", "Alphabet Inc. Class A", ["google", "alphabet"]),
        ("GOOG", "Alphabet Inc. Class C", ["google class c"]),
        ("AMZN", "Amazon.com Inc.", ["amazon"]),
        ("META", "Meta Platforms Inc.", ["meta", "facebook"]),
        ("TSLA", "Tesla Inc.", ["tesla"]),
        ("BRK-B", "Berkshire Hathaway Inc. Class B", ["berkshire hathaway", "berkshire"]),
        ("JPM", "JPMorgan Chase & Co.", ["jpmorgan", "jp morgan"]),
        ("V", "Visa Inc.", ["visa"]),
        ("MA", "Mastercard Incorporated", ["mastercard"]),
        ("UNH", "UnitedHealth Group Incorporated", ["unitedhealth", "united health"]),
        ("LLY", "Eli Lilly and Company", ["eli lilly", "lilly"]),
        ("XOM", "Exxon Mobil Corporation", ["exxon", "exxonmobil"]),
        ("AVGO", "Broadcom Inc.", ["broadcom"]),
        ("WMT", "Walmart Inc.", ["walmart"]),
        ("COST", "Costco Wholesale Corporation", ["costco"]),
        ("PG", "Procter & Gamble Company", ["procter gamble", "p&g"]),
        ("JNJ", "Johnson & Johnson", ["johnson and johnson"]),
        ("HD", "The Home Depot Inc.", ["home depot"]),
        ("BAC", "Bank of America Corporation", ["bank of america", "bofa"]),
        ("ABBV", "AbbVie Inc.", ["abbvie"]),
        ("KO", "The Coca-Cola Company", ["coca cola", "coke"]),
        ("NFLX", "Netflix Inc.", ["netflix"]),
        ("AMD", "Advanced Micro Devices Inc.", ["advanced micro devices", "amd"]),
        ("ADBE", "Adobe Inc.", ["adobe"]),
        ("CRM", "Salesforce Inc.", ["salesforce"]),
        ("ORCL", "Oracle Corporation", ["oracle"]),
        ("CSCO", "Cisco Systems Inc.", ["cisco"]),
        ("INTC", "Intel Corporation", ["intel"]),
        ("QCOM", "QUALCOMM Incorporated", ["qualcomm"]),
        ("PEP", "PepsiCo Inc.", ["pepsico", "pepsi"]),
        ("PFE", "Pfizer Inc.", ["pfizer"]),
        ("MRK", "Merck & Co. Inc.", ["merck"]),
        ("DIS", "The Walt Disney Company", ["disney"]),
        ("BA", "The Boeing Company", ["boeing"]),
        ("CAT", "Caterpillar Inc.", ["caterpillar"]),
        ("IBM", "International Business Machines Corporation", ["ibm"]),
        ("MCD", "McDonald's Corporation", ["mcdonalds", "mcdonald's"]),
        ("PYPL", "PayPal Holdings Inc.", ["paypal"]),
        ("UBER", "Uber Technologies Inc.", ["uber"]),
        ("ABNB", "Airbnb Inc.", ["airbnb"]),
        ("PLTR", "Palantir Technologies Inc.", ["palantir"]),
        ("SPY", "SPDR S&P 500 ETF Trust", ["s&p 500 etf", "sp500 etf"]),
        ("QQQ", "Invesco QQQ Trust", ["nasdaq 100 etf", "qqq"]),
        ("DIA", "SPDR Dow Jones Industrial Average ETF Trust", ["dow etf"]),
        ("IWM", "iShares Russell 2000 ETF", ["russell 2000 etf"]),
    ]

    global_rows = [
        ("BBCA", "BBCA.JK", "Bank Central Asia Tbk", "IDX", "Indonesia", "Indonesia", "IDR", ["bca", "bank central asia"], 95),
        ("BBRI", "BBRI.JK", "Bank Rakyat Indonesia Tbk", "IDX", "Indonesia", "Indonesia", "IDR", ["bri", "bank rakyat indonesia"], 90),
        ("BMRI", "BMRI.JK", "Bank Mandiri Tbk", "IDX", "Indonesia", "Indonesia", "IDR", ["mandiri", "bank mandiri"], 90),
        ("TLKM", "TLKM.JK", "Telkom Indonesia Tbk", "IDX", "Indonesia", "Indonesia", "IDR", ["telkom indonesia", "telkom"], 85),
        ("MDKA", "MDKA.JK", "Merdeka Copper Gold Tbk", "IDX", "Indonesia", "Indonesia", "IDR", ["merdeka copper gold", "merdeka copper", "merdeka gold"], 95),
        ("MBMA", "MBMA.JK", "Merdeka Battery Materials Tbk", "IDX", "Indonesia", "Indonesia", "IDR", ["merdeka battery", "merdeka battery materials"], 80),
        ("D05", "D05.SI", "DBS Group Holdings Ltd", "SGX", "Singapore", "Singapore", "SGD", ["dbs", "dbs group"], 95),
        ("O39", "O39.SI", "Oversea-Chinese Banking Corporation", "SGX", "Singapore", "Singapore", "SGD", ["ocbc"], 90),
        ("U11", "U11.SI", "United Overseas Bank Limited", "SGX", "Singapore", "Singapore", "SGD", ["uob", "united overseas bank"], 90),
        ("Z74", "Z74.SI", "Singapore Telecommunications Limited", "SGX", "Singapore", "Singapore", "SGD", ["singtel"], 85),
        ("1155", "1155.KL", "Malayan Banking Berhad", "Bursa Malaysia", "Malaysia", "Malaysia", "MYR", ["maybank", "malayan banking"], 95),
        ("1023", "1023.KL", "CIMB Group Holdings Berhad", "Bursa Malaysia", "Malaysia", "Malaysia", "MYR", ["cimb"], 90),
        ("1295", "1295.KL", "Public Bank Berhad", "Bursa Malaysia", "Malaysia", "Malaysia", "MYR", ["public bank"], 90),
        ("5347", "5347.KL", "Tenaga Nasional Berhad", "Bursa Malaysia", "Malaysia", "Malaysia", "MYR", ["tenaga nasional", "tenaga"], 85),
        ("MC", "MC.PA", "LVMH Moet Hennessy Louis Vuitton SE", "Euronext Paris", "France", "Europe", "EUR", ["lvmh"], 95),
        ("OR", "OR.PA", "L'Oreal S.A.", "Euronext Paris", "France", "Europe", "EUR", ["loreal", "l'oreal"], 85),
        ("TTE", "TTE.PA", "TotalEnergies SE", "Euronext Paris", "France", "Europe", "EUR", ["totalenergies", "total energies"], 85),
        ("SAP", "SAP", "SAP SE", "NYSE", "United States", "United States", "USD", ["sap"], 90),
        ("SIE", "SIE.DE", "Siemens Aktiengesellschaft", "XETRA", "Germany", "Europe", "EUR", ["siemens"], 90),
        ("ASML", "ASML", "ASML Holding N.V.", "NASDAQ", "United States", "United States", "USD", ["asml"], 95),
        ("NESN", "NESN.SW", "Nestle S.A.", "SIX Swiss Exchange", "Switzerland", "Europe", "CHF", ["nestle"], 90),
        ("ROG", "ROG.SW", "Roche Holding AG", "SIX Swiss Exchange", "Switzerland", "Europe", "CHF", ["roche"], 90),
        ("SHEL", "SHEL", "Shell plc", "NYSE", "United States", "United States", "USD", ["shell"], 90),
        ("HSBC", "HSBC", "HSBC Holdings plc", "NYSE", "United States", "United States", "USD", ["hsbc"], 85),
        ("BHP", "BHP.AX", "BHP Group Limited", "ASX", "Australia", "Australia", "AUD", ["bhp"], 85),
        ("CBA", "CBA.AX", "Commonwealth Bank of Australia", "ASX", "Australia", "Australia", "AUD", ["commonwealth bank", "cba"], 85),
        ("RY", "RY.TO", "Royal Bank of Canada", "TSX", "Canada", "Canada", "CAD", ["royal bank of canada", "rbc"], 85),
        ("SHOP", "SHOP.TO", "Shopify Inc.", "TSX", "Canada", "Canada", "CAD", ["shopify canada"], 80),
        ("0700", "0700.HK", "Tencent Holdings Limited", "HKEX", "Hong Kong", "Hong Kong", "HKD", ["tencent"], 90),
        ("9988", "9988.HK", "Alibaba Group Holding Limited", "HKEX", "Hong Kong", "Hong Kong", "HKD", ["alibaba hong kong"], 85),
        ("7203", "7203.T", "Toyota Motor Corporation", "Tokyo Stock Exchange", "Japan", "Japan", "JPY", ["toyota"], 90),
        ("6758", "6758.T", "Sony Group Corporation", "Tokyo Stock Exchange", "Japan", "Japan", "JPY", ["sony"], 90),
        ("005930", "005930.KS", "Samsung Electronics Co. Ltd.", "KOSPI", "South Korea", "South Korea", "KRW", ["samsung electronics", "samsung"], 90),
        ("2330", "2330.TW", "Taiwan Semiconductor Manufacturing Company", "TWSE", "Taiwan", "Taiwan", "TWD", ["tsmc taiwan"], 85),
        ("PETR4", "PETR4.SA", "Petroleo Brasileiro S.A. Petrobras", "B3", "Brazil", "Brazil", "BRL", ["petrobras"], 85),
        ("VALE3", "VALE3.SA", "Vale S.A.", "B3", "Brazil", "Brazil", "BRL", ["vale brazil"], 85),
    ]

    records = [
        symbol_record(symbol, name, "NASDAQ/NYSE", "United States", "United States", "USD", aliases, priority=90)
        for symbol, name, aliases in us
    ]
    for symbol, yahoo_symbol, name, exchange, country, market, currency, aliases, priority in global_rows:
        records.append(symbol_record(symbol, name, exchange, market, country, currency, aliases, yahoo_symbol, priority))
    return records


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


def agent_runtime_context() -> str:
    now = datetime.now().astimezone()
    return (
        "Runtime context:\n"
        f"- Current server date/time: {now.strftime('%A, %B %d, %Y %I:%M %p %Z').lstrip('0')}\n"
        "- Use this date/time context for ordinary date-sensitive questions. "
        "For market-moving news or live prices, rely on supplied backend facts."
    )


def finance_intent(text: str) -> bool:
    lower = text.lower()
    return any(word in lower for word in FINANCE_WORDS) or any(
        re.search(rf"\b{re.escape(alias)}\b", lower) for alias in ALIASES
    ) or has_symbol_like_token(text) or has_market_context(text)


def preferred_market_suffixes(text: str) -> List[str]:
    normalized = normalize_user_text(text)
    suffixes: List[str] = []
    for suffix, words in MARKET_CONTEXTS.items():
        if any(re.search(rf"\b{re.escape(word)}\b", normalized) for word in words):
            suffixes.append(suffix)
    return suffixes


def has_market_context(text: str) -> bool:
    return bool(preferred_market_suffixes(text))


def has_symbol_like_token(text: str) -> bool:
    return bool(
        re.search(r"\$[A-Za-z0-9\.\-]{1,12}\b", text)
        or re.search(r"\b[A-Z]{2,5}(?:[.\-][A-Z0-9]{1,4})?\b", text)
    )


def normalize_market_symbol(symbol: str, text: str = "") -> str:
    normalized = norm_symbol(symbol)
    if "." in normalized:
        return normalized

    for suffix in preferred_market_suffixes(text):
        if suffix == "":
            return normalized
        if normalized in MARKET_SYMBOLS.get(suffix, set()):
            return f"{normalized}{suffix}"

    for suffix, symbols in MARKET_SYMBOLS.items():
        if normalized in symbols:
            return f"{normalized}{suffix}"

    return normalized


def should_accept_direct_symbol(symbol: str, text: str) -> bool:
    if symbol in STOP or len(symbol) <= 1:
        return False
    if "." in symbol:
        return True
    suffixes = [suffix for suffix in preferred_market_suffixes(text) if suffix]
    if suffixes:
        return any(symbol.endswith(suffix) for suffix in suffixes) or any(
            symbol in MARKET_SYMBOLS.get(suffix, set()) for suffix in suffixes
        )
    return symbol in US_SYMBOLS or bool(re.fullmatch(r"[A-Z]{1,5}(?:-[A-Z])?", symbol))


def is_known_market_symbol(symbol: str) -> bool:
    if symbol in US_SYMBOLS:
        return True
    base = symbol.split(".")[0]
    if base in US_SYMBOLS:
        return True
    return any(symbol.endswith(suffix) or base in symbols for suffix, symbols in MARKET_SYMBOLS.items())


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
        symbol = normalize_market_symbol(token, text)
        if should_accept_direct_symbol(symbol, text) and symbol not in found:
            found.append(symbol)

    for token in re.findall(r"\b[A-Za-z0-9]{1,6}(?:[.\-][A-Za-z0-9]{1,4})?\b", text):
        symbol = normalize_market_symbol(token, text)
        if is_known_market_symbol(symbol) and should_accept_direct_symbol(symbol, text) and symbol not in found:
            found.append(symbol)

    for token in re.findall(r"\b[A-Z]{1,5}(?:[.\-][A-Z0-9]{1,4})?\b", text):
        symbol = normalize_market_symbol(token, text)
        if should_accept_direct_symbol(symbol, text) and symbol not in found:
            found.append(symbol)

    if has_market_context(text):
        for token in re.findall(r"\b[A-Z0-9]{2,6}(?:[.\-][A-Z0-9]{1,4})?\b", text):
            symbol = normalize_market_symbol(token, text)
            if should_accept_direct_symbol(symbol, text) and symbol not in found:
                found.append(symbol)

    return found


def ensure_supabase_symbol_master_seeded() -> None:
    if not supabase_is_configured():
        return
    try:
        existing = supabase_request(
            "GET",
            SUPABASE_SYMBOL_TABLE,
            params={"select": "symbol", "source": "eq.qfin_seed", "limit": "1"},
        ) or []
        if existing:
            return
        payload = default_symbol_master_records()
        for index in range(0, len(payload), 100):
            supabase_request(
                "POST",
                SUPABASE_SYMBOL_TABLE,
                params={"on_conflict": "symbol"},
                json_body=payload[index : index + 100],
                prefer="resolution=merge-duplicates,return=minimal",
            )
    except Exception:
        return


def clean_symbol_lookup_text(text: str) -> str:
    cleaned = re.sub(
        r"\b(analyze|analyse|compare|check|review|research|stock|ticker|company|financial|finance|about|for|on|valuation|value|summarize|summary|profitability|growth|margins|margin|cash flow|liquidity|solvency|returns|revenue|debt|earnings)\b",
        " ",
        text,
        flags=re.I,
    )
    return normalize_user_text(cleaned)


def symbol_master_terms(text: str, provided: Optional[str] = None) -> List[str]:
    terms: List[str] = []
    if provided:
        terms.append(norm_symbol(provided))
    for token in re.findall(r"\$?([A-Za-z0-9]{1,8}(?:[.\-][A-Za-z0-9]{1,5})?)\b", text):
        normalized = norm_symbol(token)
        if normalized not in STOP and normalized not in terms:
            terms.append(normalized)
    cleaned = clean_symbol_lookup_text(text)
    if cleaned and cleaned not in terms:
        terms.append(cleaned)
    return terms[:12]


def symbol_master_score(record: Dict[str, Any], term: str, text: str) -> int:
    symbol = norm_symbol(str(record.get("symbol") or ""))
    yahoo_symbol = norm_symbol(str(record.get("yahoo_symbol") or symbol))
    normalized_term = normalize_user_text(term)
    search_text = str(record.get("search_text") or "").lower()
    aliases = [normalize_user_text(str(alias)) for alias in record.get("aliases") or []]
    suffixes = preferred_market_suffixes(text)
    score = int(record.get("priority") or 0)

    if norm_symbol(term) in {symbol, yahoo_symbol}:
        score += 120
    if normalized_term and normalized_term in aliases:
        score += 95
    if normalized_term and normalized_term in search_text:
        score += 60
    for suffix in suffixes:
        if suffix == "" and "." not in yahoo_symbol:
            score += 35
        elif suffix and yahoo_symbol.endswith(suffix):
            score += 45
    return score


def local_symbol_master_candidates(term: str, text: str) -> List[Dict[str, Any]]:
    normalized_term = normalize_user_text(term)
    raw_symbol = norm_symbol(term)
    rows = []
    for record in default_symbol_master_records():
        symbol = norm_symbol(str(record.get("symbol") or ""))
        yahoo_symbol = norm_symbol(str(record.get("yahoo_symbol") or symbol))
        search_text = str(record.get("search_text") or "")
        if (
            raw_symbol in {symbol, yahoo_symbol}
            or (normalized_term and normalized_term in search_text)
        ):
            rows.append(record)
    return sorted(rows, key=lambda row: symbol_master_score(row, term, text), reverse=True)


def fetch_symbol_master_candidates(term: str, text: str) -> List[Dict[str, Any]]:
    if not supabase_is_configured():
        return local_symbol_master_candidates(term, text)
    ensure_supabase_symbol_master_seeded()
    select = "symbol,yahoo_symbol,name,exchange,market,country,currency,aliases,search_text,priority,active"
    normalized_term = normalize_user_text(term)
    raw_symbol = norm_symbol(term)
    rows: List[Dict[str, Any]] = []

    try:
        if re.fullmatch(r"[A-Z0-9]{1,8}(?:[.\-][A-Z0-9]{1,5})?", raw_symbol):
            for field in ("symbol", "yahoo_symbol"):
                rows.extend(
                    supabase_request(
                        "GET",
                        SUPABASE_SYMBOL_TABLE,
                        params={"select": select, "active": "eq.true", field: f"eq.{raw_symbol}", "limit": "10"},
                    ) or []
                )
        if len(normalized_term) >= 2:
            rows.extend(
                supabase_request(
                    "GET",
                    SUPABASE_SYMBOL_TABLE,
                    params={
                        "select": select,
                        "active": "eq.true",
                        "search_text": f"ilike.*{normalized_term}*",
                        "limit": "20",
                    },
                ) or []
            )
    except Exception:
        return local_symbol_master_candidates(term, text)

    deduped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = norm_symbol(str(row.get("yahoo_symbol") or row.get("symbol") or ""))
        if key:
            deduped[key] = row
    return sorted(deduped.values(), key=lambda row: symbol_master_score(row, term, text), reverse=True)


def resolve_from_symbol_master(text: str, provided: Optional[str] = None) -> Optional[str]:
    cache_key = f"{provided or ''}|{normalize_user_text(text)}"
    cached = SYMBOL_MASTER_CACHE.get(cache_key)
    if cached:
        return str(cached.get("symbol") or "")

    best_record: Optional[Dict[str, Any]] = None
    best_score = 0
    for term in symbol_master_terms(text, provided):
        candidates = fetch_symbol_master_candidates(term, text)
        if not candidates:
            continue
        score = symbol_master_score(candidates[0], term, text)
        if score > best_score:
            best_record = candidates[0]
            best_score = score

    if not best_record or best_score < 70:
        return None

    resolved = norm_symbol(str(best_record.get("yahoo_symbol") or best_record.get("symbol") or ""))
    if resolved:
        SYMBOL_MASTER_CACHE[cache_key] = {"symbol": resolved, "record": best_record}
    return resolved or None


def learn_symbol_master(query: str, symbol: str, quote: Optional[Dict[str, Any]] = None) -> None:
    if not supabase_is_configured() or not symbol:
        return
    quote = quote or {}
    name = (
        quote.get("longname")
        or quote.get("shortname")
        or quote.get("name")
        or clean_symbol_lookup_text(query)
        or symbol
    )
    exchange = quote.get("exchDisp") or quote.get("exchange") or "Yahoo Finance"
    row = symbol_record(
        symbol=symbol,
        yahoo_symbol=symbol,
        name=str(name),
        exchange=str(exchange),
        market=str(quote.get("market") or exchange),
        country=str(quote.get("region") or ""),
        currency=str(quote.get("currency") or ""),
        aliases=[clean_symbol_lookup_text(query)],
        priority=40,
        source="yahoo_search",
    )
    try:
        supabase_request(
            "POST",
            SUPABASE_SYMBOL_TABLE,
            params={"on_conflict": "symbol"},
            json_body=row,
            prefer="resolution=merge-duplicates,return=minimal",
        )
    except Exception:
        return


def yahoo_quote_score(item: Dict[str, Any], query: str) -> int:
    symbol = norm_symbol(str(item.get("symbol") or ""))
    name = " ".join(
        str(item.get(field) or "")
        for field in ("shortname", "longname", "name", "exchDisp", "exchange")
    ).lower()
    normalized_query = normalize_user_text(query)
    query_words = [word for word in normalized_query.split() if len(word) > 2]
    suffixes = preferred_market_suffixes(query)
    score = 0

    if symbol:
        score += 5
    for index, suffix in enumerate(suffixes):
        if suffix == "" and "." not in symbol:
            score += 55 - index
        elif suffix and symbol.endswith(suffix):
            score += 60 - index
    if not suffixes and "." not in symbol:
        score += 20

    if item.get("quoteType") == "EQUITY":
        score += 10
    exchange_text = f"{item.get('exchDisp', '')} {item.get('exchange', '')}".lower()
    if not suffixes and any(exchange in exchange_text for exchange in ("nasdaq", "nyse", "american")):
        score += 15
    if any(word in name for word in query_words):
        score += sum(3 for word in query_words if word in name)
    if suffixes and "." in symbol and not any(symbol.endswith(suffix) for suffix in suffixes if suffix):
        score -= 20
    return score


def pick_best_yahoo_quote_record(quotes: List[Dict[str, Any]], query: str) -> Optional[Dict[str, Any]]:
    if not quotes:
        return None
    ranked = sorted(quotes, key=lambda item: yahoo_quote_score(item, query), reverse=True)
    best = ranked[0]
    if yahoo_quote_score(best, query) <= 0:
        return None
    return best


def pick_best_yahoo_quote(quotes: List[Dict[str, Any]], query: str) -> Optional[str]:
    best = pick_best_yahoo_quote_record(quotes, query)
    return norm_symbol(str(best["symbol"])) if best else None


def search_yahoo_quotes(query: str, quotes_count: int = 25) -> List[Dict[str, Any]]:
    try:
        response = httpx.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={
                "q": query,
                "quotesCount": quotes_count,
                "newsCount": 0,
                "enableFuzzyQuery": True,
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15.0,
        )
        if response.status_code >= 400:
            return []
        return [
            item
            for item in response.json().get("quotes", [])
            if item.get("symbol") and item.get("quoteType") in {"EQUITY", "ETF", "MUTUALFUND", "INDEX"}
        ]
    except Exception:
        return []


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
        direct_candidates = extract_symbol_candidates(cleaned)
        if direct_candidates:
            return direct_candidates[0]

        quotes = search_yahoo_quotes(cleaned)
        best_record = pick_best_yahoo_quote_record(quotes, query)
        if best_record:
            symbol = norm_symbol(str(best_record["symbol"]))
            learn_symbol_master(query, symbol, best_record)
            return symbol

        for suffix in preferred_market_suffixes(query):
            if suffix:
                best_record = pick_best_yahoo_quote_record(search_yahoo_quotes(f"{cleaned} {suffix}"), query)
                if best_record:
                    symbol = norm_symbol(str(best_record["symbol"]))
                    learn_symbol_master(query, symbol, best_record)
                    return symbol
    except Exception:
        return None
    return None


def resolve_single_ticker(text: str, provided: Optional[str] = None, allow_search: bool = True) -> Optional[str]:
    if provided:
        return resolve_from_symbol_master(text, provided) or normalize_market_symbol(provided, text)

    candidates = extract_symbol_candidates(text)
    if candidates:
        return candidates[0]

    master_symbol = resolve_from_symbol_master(text)
    if master_symbol:
        return master_symbol

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

    if re.search(r"\b(headlines?|breaking|top stories|latest)\b", text, flags=re.I) and re.search(r"\b(news|market|markets|stocks?|crypto|bonds?|etfs?)\b", text, flags=re.I):
        category = "Stocks"
        for option in ["Crypto", "Stocks", "Bonds", "ETFs", "Other"]:
            if option.lower() in text.lower():
                category = option
                break
        return {"kind": "headlines", "category": category}

    if "news" in text.lower():
        category = "Stocks"
        for option in ["Crypto", "Stocks", "Bonds", "ETFs", "Other"]:
            if option.lower() in text.lower():
                category = option
                break
        return {"kind": "news", "category": category}

    ticker = resolve_single_ticker(text, provided_ticker)
    if ticker:
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


def get_cached_financial_data(ticker: str) -> Optional[Dict[str, Any]]:
    key = ticker.strip().upper()
    cached = FINANCIAL_DATA_CACHE.get(key)
    if not cached:
        return None
    age_seconds = (datetime.now(timezone.utc) - cached["stored_at"]).total_seconds()
    if age_seconds > FINANCIAL_DATA_CACHE_TTL_SECONDS:
        FINANCIAL_DATA_CACHE.pop(key, None)
        return None
    return cached["data"]


def store_cached_financial_data(ticker: str, data: Dict[str, Any]) -> Dict[str, Any]:
    FINANCIAL_DATA_CACHE[ticker.strip().upper()] = {
        "data": data,
        "stored_at": datetime.now(timezone.utc),
    }
    return data


async def fetch_financial_data_async(ticker: str, timeout_seconds: float = 25.0) -> Dict[str, Any]:
    timeout_seconds = read_float_env("FINANCIAL_DATA_TIMEOUT_SECONDS", timeout_seconds)
    cached = get_cached_financial_data(ticker)
    if cached is not None:
        return cached

    try:
        data = await asyncio.wait_for(
            asyncio.to_thread(fetch_financial_data, ticker),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        data = {
            "ticker": ticker,
            "data_status": "unavailable",
            "error": f"Financial data request timed out after {timeout_seconds:.0f}s.",
        }

    return store_cached_financial_data(ticker, data)


def hash_slice(seed_text: str, offset: int) -> int:
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    start = (offset * 2) % (len(digest) - 2)
    return int(digest[start:start + 2], 16)


def build_model_profile(name: str, summary: str, tags: List[str], code: str) -> Dict[str, str]:
    text = " ".join([name, summary, " ".join(tags), code]).lower()

    if "crypto" in text:
        universe = "Large-cap crypto pairs"
        benchmark = "BTC-USD"
    elif "carry" in text or "basket" in text or "portfolio" in text:
        universe = "Liquid US large-cap equities"
        benchmark = "SPY"
    else:
        universe = "Liquid US equities and ETFs"
        benchmark = "SPY"

    if "macd" in text or "trend" in text or "momentum" in text:
        horizon = "Swing horizon (3 to 15 sessions)"
        rebalance = "Daily close review"
        execution_style = "Trend-following"
    elif "rsi" in text or "mean reversion" in text or "pullback" in text:
        horizon = "Short swing horizon (2 to 8 sessions)"
        rebalance = "Daily close review"
        execution_style = "Mean reversion"
    elif "dcf" in text or "valuation" in text or "quality" in text:
        horizon = "Medium horizon (2 to 6 weeks)"
        rebalance = "Weekly rebalance"
        execution_style = "Fundamental overlay"
    else:
        horizon = "Medium horizon (1 to 4 weeks)"
        rebalance = "Weekly rebalance"
        execution_style = "Systematic long/short"

    if "volatility" in text or "regime" in text or "risk" in text:
        risk_style = "Adaptive risk control"
    elif "earnings" in text or "event" in text:
        risk_style = "Event-driven risk"
    else:
        risk_style = "Balanced risk budget"

    data_inputs = "Daily OHLCV candles"
    if "dcf" in text or "quality" in text or "cash" in text:
        data_inputs += " plus company fundamentals"
    if "vol" in text or "volatility" in text:
        data_inputs += " and realized volatility"

    live_use = "Paper trade first, then add fees, slippage, and position limits before live deployment."

    return {
        "universe": universe,
        "benchmark": benchmark,
        "rebalance": rebalance,
        "horizon": horizon,
        "execution_style": execution_style,
        "risk_style": risk_style,
        "data_inputs": data_inputs,
        "live_use": live_use,
    }


def build_model_series(seed_text: str, periods: int = 12) -> List[Dict[str, Any]]:
    equity = 100.0
    benchmark = 100.0
    peak = equity
    series: List[Dict[str, Any]] = []

    for index in range(periods):
        alpha = ((hash_slice(seed_text, index) % 17) - 4) / 100
        beta = ((hash_slice(seed_text, index + 17) % 11) - 3) / 100
        equity *= 1 + alpha
        benchmark *= 1 + beta
        peak = max(peak, equity)
        drawdown = max(0.0, (peak - equity) / peak * 100)
        series.append(
            {
                "label": MODEL_PERIOD_LABELS[index % len(MODEL_PERIOD_LABELS)],
                "equity": round(equity, 2),
                "benchmark": round(benchmark, 2),
                "drawdown": round(drawdown, 2),
            }
        )

    return series


def build_model_status(stats: Dict[str, str]) -> str:
    annual_return = as_float(str(stats.get("annual_return", "")).replace("%", ""))
    sharpe = as_float(stats.get("sharpe"))
    max_drawdown = as_float(str(stats.get("max_drawdown", "")).replace("%", ""))

    if sharpe is not None and annual_return is not None and sharpe >= 1.5 and annual_return >= 14:
        return "paper-ready"
    if max_drawdown is not None and abs(max_drawdown) >= 18:
        return "high-risk"
    return "research"


def build_model_highlights(stats: Dict[str, str], profile: Dict[str, str]) -> List[str]:
    return [
        f"Universe: {profile['universe']}",
        f"Benchmark: {profile['benchmark']}",
        f"Cadence: {profile['rebalance']}",
        f"Risk posture: {profile['risk_style']}",
    ]


def build_general_prompt(query: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{agent_runtime_context()}"},
        {"role": "user", "content": query},
    ]


def build_public_data_prompt(query: str, facts: Dict[str, Any]) -> List[Dict[str, str]]:
    fact_block = serialize_agent_facts(facts)
    user_content = (
        f"User request: {query}\n"
        f"Public API facts:\n{fact_block}\n"
        "Answer the user naturally. Use the public API facts where relevant, but do not overstate them."
    )
    return [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{PUBLIC_DATA_PROMPT}\n\n{agent_runtime_context()}"},
        {"role": "user", "content": user_content},
    ]


def serialize_agent_facts(facts: Any) -> str:
    if facts is None:
        return "No backend facts were required for this request."
    try:
        return json.dumps(facts, ensure_ascii=True, indent=2, default=str)
    except Exception:
        return str(facts)


def build_finance_prompt(query: str, route: Dict[str, Any], facts: Any) -> List[Dict[str, str]]:
    route_kind = route["kind"]
    fact_block = serialize_agent_facts(facts)
    if route_kind == "comparison":
        user_content = (
            f"User request: {query}\n"
            f"Internal route: exact ticker comparison\n"
            f"Required tickers: {route['tickers']}\n"
            f"Topic: {route['topic']}\n"
            f"Backend facts:\n{fact_block}\n"
            "Use only these exact tickers. Do not substitute any other symbol. "
            "Write a detailed side-by-side finance comparison and clearly state what data is missing if any metric is unavailable. "
            "Do not mention the internal route or backend mechanics in the final answer."
        )
    elif route_kind == "company":
        user_content = (
            f"User request: {query}\n"
            f"Internal route: single company analysis\n"
            f"Resolved ticker: {route['ticker']}\n"
            f"Backend facts:\n{fact_block}\n"
            "Use only this backend data. If the user asked about the latest quarter, focus on the latest quarter context first, then the broader fundamentals. "
            "Do not mention the internal route or backend mechanics in the final answer."
        )
    elif route_kind == "news":
        user_content = (
            f"User request: {query}\n"
            f"Internal route: market news summary\n"
            f"Category: {route['category']}\n"
            f"Backend facts:\n{fact_block}\n"
            "Summarize the five news items, explain what matters most, and mention market sentiment. "
            "Do not mention the internal route or backend mechanics in the final answer."
        )
    else:
        user_content = (
            f"User request: {query}\n"
            "Internal route: finance concept\n"
            "Answer as a finance expert. Use formulas, interpretation, and caveats where useful."
        )

    return [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{FINANCE_DETAIL_PROMPT}\n\n{AGENT_SOURCE_NOTE}\n\n{agent_runtime_context()}"},
        {"role": "user", "content": user_content},
    ]


def build_headline_digest(news: Dict[str, Any], limit: int = 5) -> str:
    lines = ["Here are the latest market headlines I found:"]
    for item in news.get("news", [])[:limit]:
        headline = clean_text(str(item.get("headline") or "Market update"))
        source = item.get("source") or {}
        source_name = clean_text(str(source.get("name") or "Aggregated market commentary"))
        teaser = clean_text(str(item.get("teaser") or ""))
        lines.append(f"- {headline} ({source_name})")
        if teaser:
            lines.append(f"  {teaser}")
    return "\n".join(lines)


def build_evidence_packet(query: str, route: Dict[str, Any], facts: Any, used_live_data: bool) -> EvidencePacket:
    items: List[EvidenceItem] = []
    gaps: List[str] = []
    warnings: List[str] = []

    if route["kind"] in {"company", "comparison"}:
        fact_map = facts if isinstance(facts, dict) else {}
        if route["kind"] == "company":
            fact_map = {route["ticker"]: facts}
        for ticker, payload in fact_map.items():
            payload = payload or {}
            data_status = payload.get("data_status")
            if data_status != "available":
                gaps.append(f"Live financial data was incomplete for {ticker}.")
            items.append(
                EvidenceItem(
                    kind="financial_data",
                    label=str(ticker),
                    source=str(payload.get("source") or "Yahoo Finance via yfinance"),
                    summary=clean_text(
                        f"{payload.get('company_name') or ticker}: data_status={payload.get('data_status') or 'unknown'}."
                    ),
                    payload=payload,
                )
            )
    elif route["kind"] in {"news", "headlines"}:
        for item in (facts or {}).get("news", [])[:5]:
            source = item.get("source") or {}
            items.append(
                EvidenceItem(
                    kind="headline",
                    label=clean_text(str(item.get("headline") or "Market update")),
                    source=clean_text(str(source.get("name") or "Aggregated market commentary")),
                    summary=clean_text(str(item.get("teaser") or item.get("headline") or "Market update")),
                    payload=item,
                )
            )
        if not items:
            gaps.append("No live headlines were returned by the backend.")
    elif isinstance(facts, dict) and facts.get("facts"):
        for fact in facts.get("facts", []):
            payload = fact.get("data")
            items.append(
                EvidenceItem(
                    kind="public_api",
                    label=clean_text(str(fact.get("source") or "Public API")),
                    source=clean_text(str(fact.get("source") or "Public API")),
                    summary=clean_text(str(payload)[:240]),
                    payload=payload,
                )
            )
        if facts.get("errors"):
            warnings.extend(facts.get("errors")[:5])

    return EvidencePacket(
        trace_id=make_id("agent"),
        query=query,
        route=route,
        gathered_at=utc_now(),
        items=items,
        used_live_data=used_live_data,
        gaps=gaps,
        warnings=warnings,
    )


def run_agent_risk_review(route: Dict[str, Any], facts: Any, content: str) -> AgentRiskReview:
    allowed_tickers: List[str] = []
    if route.get("ticker"):
        allowed_tickers.append(route["ticker"])
    if route.get("tickers"):
        allowed_tickers.extend(route["tickers"])

    warnings: List[str] = []
    missing_data: List[str] = []

    if route["kind"] == "company" and isinstance(facts, dict) and facts.get("data_status") != "available":
        missing_data.append(f"Financial data for {route['ticker']} is incomplete or unavailable.")
    elif route["kind"] == "comparison" and isinstance(facts, dict):
        for ticker in route.get("tickers", []):
            payload = facts.get(ticker) or {}
            if payload.get("data_status") != "available":
                missing_data.append(f"Financial data for {ticker} is incomplete or unavailable.")

    if allowed_tickers:
        mentioned = [symbol for symbol in extract_symbol_candidates(content) if symbol not in allowed_tickers]
        clean_mentions = [symbol for symbol in mentioned if symbol not in STOP]
        if clean_mentions:
            warnings.append(
                "Model answer mentioned extra ticker-like symbols outside the requested scope: "
                + ", ".join(sorted(set(clean_mentions))[:6])
            )

    status: Literal["pass", "review"] = "review" if warnings or missing_data else "pass"
    return AgentRiskReview(
        status=status,
        warnings=warnings,
        missing_data=missing_data,
        allowed_tickers=allowed_tickers,
    )


def finalize_agent_content(content: str, review: AgentRiskReview) -> str:
    notes: List[str] = []
    if review.missing_data:
        notes.extend(review.missing_data)
    if review.warnings:
        notes.extend(review.warnings)
    if not notes:
        return content
    note_block = "\n".join(f"- {note}" for note in notes)
    if "Caveat" in content or "caveat" in content:
        return content
    return f"{content}\n\n**Caveat**\n{note_block}"


def remember_agent_session(
    evidence: EvidencePacket,
    review: AgentRiskReview,
    content: str,
) -> None:
    AGENT_SESSION_LOGS.insert(
        0,
        {
            "trace_id": evidence.trace_id,
            "query": evidence.query,
            "route": evidence.route,
            "used_live_data": evidence.used_live_data,
            "gathered_at": evidence.gathered_at,
            "risk_review": review.dict(),
            "content_preview": content[:400],
        },
    )
    del AGENT_SESSION_LOGS[25:]


async def ask_qwen(messages: List[Dict[str, str]]) -> str:
    response = await call_qwen(messages)
    return clean_text(response["choices"][0]["message"]["content"])


async def generate_agent_reply(query: str, provided_ticker: Optional[str] = None) -> Dict[str, Any]:
    route = classify_message(query, provided_ticker)

    if route["kind"] == "casual":
        return {"route": route, "content": route["reply"], "facts": None, "used_live_data": False}

    if route["kind"] == "time":
        return {"route": route, "content": local_time_reply(), "facts": None, "used_live_data": False}

    if route["kind"] in {"news", "headlines"}:
        news = await generate_news(normalize_category(route["category"]))
        evidence = build_evidence_packet(query, route, news, used_live_data=True)
        if not qwen_is_configured():
            content = build_headline_digest(news)
        else:
            prompt_route = {**route, "kind": "news"}
            content = await ask_qwen(build_finance_prompt(query, prompt_route, news))
        review = run_agent_risk_review(route, news, content)
        content = finalize_agent_content(content, review)
        remember_agent_session(evidence, review, content)
        return {
            "route": route,
            "content": content,
            "facts": news,
            "used_live_data": True,
            "evidence": evidence.dict(),
            "risk_review": review.dict(),
        }

    if route["kind"] == "comparison":
        comparison_results = await asyncio.gather(
            *(fetch_financial_data_async(ticker) for ticker in route["tickers"])
        )
        facts = {
            ticker: data
            for ticker, data in zip(route["tickers"], comparison_results)
        }
        evidence = build_evidence_packet(query, route, facts, used_live_data=True)
        if not qwen_is_configured():
            content = (
                f"Qwen is not configured, but I resolved the request to {route['tickers'][0]} and {route['tickers'][1]}. "
                "Connect the DashScope key to let QFin write the full comparison."
            )
        else:
            content = await ask_qwen(build_finance_prompt(query, route, facts))
        review = run_agent_risk_review(route, facts, content)
        content = finalize_agent_content(content, review)
        remember_agent_session(evidence, review, content)
        return {
            "route": route,
            "content": content,
            "facts": facts,
            "used_live_data": True,
            "evidence": evidence.dict(),
            "risk_review": review.dict(),
        }

    if route["kind"] == "company":
        facts = await fetch_financial_data_async(route["ticker"])
        evidence = build_evidence_packet(query, route, facts, used_live_data=True)
        if not qwen_is_configured():
            content = (
                f"I resolved this request to {route['ticker']}, but Qwen is not configured on the backend right now. "
                "Add the DashScope key in Render so I can write the full report."
            )
        else:
            content = await ask_qwen(build_finance_prompt(query, route, facts))
        review = run_agent_risk_review(route, facts, content)
        content = finalize_agent_content(content, review)
        remember_agent_session(evidence, review, content)
        return {
            "route": route,
            "content": content,
            "facts": facts,
            "used_live_data": True,
            "evidence": evidence.dict(),
            "risk_review": review.dict(),
        }

    if route["kind"] == "finance_concept":
        if not qwen_is_configured():
            return {
                "route": route,
                "content": "The backend is connected, but Qwen is unavailable right now. Add the DashScope key to enable full finance explanations.",
                "facts": None,
                "used_live_data": False,
            }
        content = await ask_qwen(build_finance_prompt(query, route, None))
        review = run_agent_risk_review(route, None, content)
        content = finalize_agent_content(content, review)
        evidence = build_evidence_packet(query, route, None, used_live_data=False)
        remember_agent_session(evidence, review, content)
        return {
            "route": route,
            "content": content,
            "facts": None,
            "used_live_data": False,
            "evidence": evidence.dict(),
            "risk_review": review.dict(),
        }

    if not qwen_is_configured():
        return {
            "route": route,
            "content": "The backend is connected, but Qwen is unavailable right now. Add the DashScope key in Render to enable full chat responses.",
            "facts": None,
            "used_live_data": False,
        }

    public_facts = await fetch_public_api_facts(query)
    if public_facts.get("facts"):
        content = await ask_qwen(build_public_data_prompt(query, public_facts))
        route = {**route, "public_data": True}
        evidence = build_evidence_packet(query, route, public_facts, used_live_data=True)
        review = run_agent_risk_review(route, public_facts, content)
        content = finalize_agent_content(content, review)
        remember_agent_session(evidence, review, content)
        return {
            "route": route,
            "content": content,
            "facts": public_facts,
            "used_live_data": True,
            "evidence": evidence.dict(),
            "risk_review": review.dict(),
        }

    content = await ask_qwen(build_general_prompt(query))
    review = run_agent_risk_review(route, None, content)
    content = finalize_agent_content(content, review)
    evidence = build_evidence_packet(query, route, None, used_live_data=False)
    remember_agent_session(evidence, review, content)
    return {
        "route": route,
        "content": content,
        "facts": None,
        "used_live_data": False,
        "evidence": evidence.dict(),
        "risk_review": review.dict(),
    }


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
    stats = {
        "annual_return": f"{annual_return:.1f}%",
        "sharpe": f"{sharpe:.2f}",
        "max_drawdown": f"-{max_drawdown:.1f}%",
        "win_rate": f"{win_rate:.1f}%",
    }
    profile = build_model_profile(name, summary, tags, seed_text)
    return {
        "id": make_id("model"),
        "name": name,
        "author": author,
        "summary": summary,
        "tags": tags,
        "score": 8 + int(digest[8:10], 16) % 22,
        "created_at": utc_now(),
        "stats": stats,
        "profile": profile,
        "status": build_model_status(stats),
        "series": build_model_series(f"{name}\n{seed_text}"),
        "highlights": build_model_highlights(stats, profile),
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
    name = clean_text(str(record.get("name") or "Untitled model"))
    summary = clean_text(str(record.get("summary") or ""))
    code = str(record.get("code") or "")
    normalized_stats = stats if isinstance(stats, dict) else {}
    tags_value = tags if isinstance(tags, list) else []
    profile = record.get("profile")
    if not isinstance(profile, dict):
        profile = build_model_profile(name, summary, tags_value, code)
    series = record.get("series")
    if not isinstance(series, list) or not series:
        series = build_model_series(f"{name}\n{code}")
    highlights = record.get("highlights")
    if not isinstance(highlights, list) or not highlights:
        highlights = build_model_highlights(normalized_stats, profile)
    return {
        "id": record.get("id") or make_id("model"),
        "name": name,
        "author": clean_text(str(record.get("author") or "Unknown author")),
        "summary": summary,
        "code": code,
        "ticker": str(record.get("ticker") or profile.get("benchmark") or "SPY"),
        "tags": tags_value,
        "stats": normalized_stats,
        "profile": profile,
        "series": series,
        "highlights": highlights,
        "status": str(record.get("status") or build_model_status(normalized_stats)),
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


def resolve_builder_ticker(name: str, summary: str, code: str, requested: Optional[str] = None) -> str:
    if requested and re.fullmatch(TICKER_RE, requested.strip()):
        return norm_symbol(requested)

    text = " ".join([name, summary, code])
    ticker = resolve_single_ticker(text, allow_search=False)
    if ticker:
        return ticker

    lowered = text.lower()
    if "crypto" in lowered or "bitcoin" in lowered or "btc" in lowered:
        return "BTC-USD"
    if "bond" in lowered or "treasury" in lowered or "duration" in lowered or "rate" in lowered:
        return "TLT"
    if "ipo" in lowered:
        return "IPO"
    if "nasdaq" in lowered or "technology" in lowered or "ai" in lowered:
        return "QQQ"
    return "SPY"


def fetch_price_history(ticker: str, period: str = "1y") -> Dict[str, Any]:
    try:
        import yfinance as yf

        frame = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
        if frame is None or frame.empty or "Close" not in frame:
            raise RuntimeError("No close-price history returned.")

        rows: List[Dict[str, Any]] = []
        closes = frame["Close"].dropna()
        volume_series = frame["Volume"] if "Volume" in frame else None
        for index, value in closes.items():
            volume = None
            if volume_series is not None:
                volume = as_float(volume_series.loc[index])
            rows.append(
                {
                    "date": str(index.date()) if hasattr(index, "date") else str(index)[:10],
                    "close": float(value),
                    "volume": volume,
                }
            )

        if len(rows) >= 20:
            return {"ticker": ticker, "rows": rows, "source": "Yahoo Finance via yfinance"}
    except Exception as exc:
        fallback = build_fallback_price_history(ticker)
        fallback["warning"] = str(exc)
        return fallback

    return build_fallback_price_history(ticker)


def build_fallback_price_history(ticker: str, periods: int = 252) -> Dict[str, Any]:
    seed = hashlib.sha256(ticker.encode("utf-8")).hexdigest()
    price = 100.0 + int(seed[:2], 16) % 40
    rows = []
    for index in range(periods):
        wave = math.sin(index / 13) * 0.006
        drift = ((int(seed[(index % 24):(index % 24) + 2], 16) % 7) - 2) / 1000
        price *= 1 + wave + drift
        rows.append(
            {
                "date": f"T-{periods - index}",
                "close": round(price, 2),
                "volume": 1_000_000 + (index * 13791) % 800_000,
            }
        )
    return {"ticker": ticker, "rows": rows, "source": "deterministic fallback history"}


def strategy_family(name: str, summary: str, code: str) -> str:
    text = " ".join([name, summary, code]).lower()
    if "rsi" in text or "mean reversion" in text or "pullback" in text:
        return "mean-reversion"
    if "macd" in text or "moving average" in text or "momentum" in text or "trend" in text:
        return "trend-following"
    if "monte" in text or "gbm" in text or "scenario" in text:
        return "simulation"
    if "bond" in text or "duration" in text or "rate shock" in text:
        return "rates"
    if "lbo" in text or "waterfall" in text or "irr" in text:
        return "deal-model"
    if "ipo" in text or "new issue" in text or "ecm" in text:
        return "event-monitor"
    return "adaptive-momentum"


def simple_mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def simple_std(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = simple_mean(values)
    variance = sum((value - avg) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(max(variance, 0.0))


def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    if len(prices) <= period:
        return None
    gains: List[float] = []
    losses: List[float] = []
    window = prices[-period - 1:]
    for previous, current in zip(window, window[1:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(abs(min(change, 0.0)))
    avg_loss = simple_mean(losses)
    if avg_loss == 0:
        return 100.0
    relative_strength = simple_mean(gains) / avg_loss
    return 100 - (100 / (1 + relative_strength))


def signal_for_family(family: str, prices: List[float], index: int) -> float:
    history = prices[: index + 1]
    if len(history) < 21:
        return 0.0

    price = history[-1]
    ma20 = simple_mean(history[-20:])
    ma50 = simple_mean(history[-50:]) if len(history) >= 50 else ma20

    if family == "mean-reversion":
        rsi = calculate_rsi(history) or 50.0
        if rsi < 38 and price >= ma20 * 0.94:
            return 1.0
        if rsi > 68:
            return 0.0
        return 0.5 if price > ma50 else 0.0

    if family == "trend-following":
        return 1.0 if ma20 > ma50 and price > ma20 else 0.0

    if family == "simulation":
        vol = simple_std([(history[i] / history[i - 1] - 1) for i in range(max(1, len(history) - 21), len(history))])
        return 0.7 if vol < 0.03 and price > ma50 else 0.35

    if family == "rates":
        return 1.0 if price > ma20 else 0.25

    if family == "deal-model":
        return 0.6 if price > ma50 else 0.2

    if family == "event-monitor":
        five_day = price / history[-5] - 1 if len(history) >= 5 and history[-5] else 0.0
        return 1.0 if five_day > 0.01 and price > ma20 else 0.0

    return 1.0 if price > ma20 and ma20 >= ma50 else 0.25


def make_backtest_series(rows: List[Dict[str, Any]], equity_curve: List[float], benchmark_curve: List[float]) -> List[Dict[str, Any]]:
    if not equity_curve:
        return build_model_series("empty-builder-series")

    points = min(12, len(equity_curve))
    if points <= 1:
        selected = [0]
    else:
        selected = sorted({round(index * (len(equity_curve) - 1) / (points - 1)) for index in range(points)})

    series = []
    peak = 100.0
    for index in selected:
        equity = equity_curve[index]
        benchmark = benchmark_curve[index]
        peak = max(peak, max(equity_curve[: index + 1]))
        drawdown = max(0.0, (peak - equity) / peak * 100) if peak else 0.0
        date_label = rows[index + 1]["date"] if index + 1 < len(rows) else rows[index]["date"]
        series.append(
            {
                "label": str(date_label)[5:] if len(str(date_label)) >= 10 else str(date_label),
                "equity": round(equity, 2),
                "benchmark": round(benchmark, 2),
                "drawdown": round(drawdown, 2),
            }
        )
    return series


def run_builder_backtest(name: str, code: str, author: Optional[str], summary: str, ticker: str) -> Dict[str, Any]:
    history = fetch_price_history(ticker)
    rows = history["rows"]
    closes = [float(row["close"]) for row in rows if as_float(row.get("close")) is not None]
    family = strategy_family(name, summary, code)

    equity = 100.0
    benchmark = 100.0
    equity_curve: List[float] = []
    benchmark_curve: List[float] = []
    strategy_returns: List[float] = []
    benchmark_returns: List[float] = []
    positions: List[float] = []

    for index in range(1, len(closes)):
        daily_return = closes[index] / closes[index - 1] - 1 if closes[index - 1] else 0.0
        position = signal_for_family(family, closes, index - 1)
        strategy_return = daily_return * position
        equity *= 1 + strategy_return
        benchmark *= 1 + daily_return
        equity_curve.append(equity)
        benchmark_curve.append(benchmark)
        strategy_returns.append(strategy_return)
        benchmark_returns.append(daily_return)
        positions.append(position)

    if not equity_curve:
        return builder_run_output_fallback(name, code, author, summary, ticker, history.get("source", "fallback"))

    days = max(len(strategy_returns), 1)
    annual_return = (equity_curve[-1] / 100) ** (252 / days) - 1
    benchmark_return = (benchmark_curve[-1] / 100) ** (252 / days) - 1
    daily_std = simple_std(strategy_returns)
    sharpe = (simple_mean(strategy_returns) / daily_std * math.sqrt(252)) if daily_std else 0.0

    peak = 100.0
    drawdowns = []
    for value in equity_curve:
        peak = max(peak, value)
        drawdowns.append((peak - value) / peak if peak else 0.0)

    position_changes = sum(1 for previous, current in zip(positions, positions[1:]) if previous != current)
    turnover = position_changes / max(len(positions), 1) * 252
    active_returns = [value for value, position in zip(strategy_returns, positions) if position > 0]
    win_rate = sum(1 for value in active_returns if value > 0) / len(active_returns) if active_returns else 0.0

    stats = {
        "annual_return": f"{annual_return * 100:.1f}%",
        "benchmark_return": f"{benchmark_return * 100:.1f}%",
        "sharpe": f"{sharpe:.2f}",
        "max_drawdown": f"-{max(drawdowns) * 100:.1f}%",
        "turnover": f"{turnover:.1f}%",
        "win_rate": f"{win_rate * 100:.1f}%",
    }

    profile = build_model_profile(name, summary, ["builder", family], code)
    profile.update(
        {
            "benchmark": ticker,
            "strategy_family": family.replace("-", " ").title(),
            "data_source": history.get("source", "unknown"),
            "data_window": f"{len(closes)} daily closes",
            "live_use": "Paper trade first. Add fees, slippage, limits, and broker execution rules before live deployment.",
        }
    )

    notes = [
        f"Backtest used {len(closes)} daily closes for {ticker}.",
        "The backend classifies the model text and runs a guarded strategy template instead of executing arbitrary uploaded code.",
        "Results are hypothetical and exclude fees, slippage, borrow costs, taxes, and execution latency.",
    ]
    if history.get("warning"):
        notes.append(f"Live price fetch warning: {history['warning']}")

    return {
        "name": clean_text(name),
        "author": clean_text(author or "Private workspace"),
        "summary": clean_text(summary or f"{name} ran a guarded {family.replace('-', ' ')} backtest on {ticker}."),
        "ticker": ticker,
        "stats": stats,
        "profile": profile,
        "status": build_model_status(stats),
        "series": make_backtest_series(rows, equity_curve, benchmark_curve),
        "highlights": build_model_highlights(stats, profile),
        "validation": [
            {"label": "Ticker data", "status": "pass", "detail": f"Loaded {len(closes)} price points for {ticker}."},
            {"label": "Strategy parser", "status": "pass", "detail": f"Matched this model to {family.replace('-', ' ')} logic."},
            {"label": "Risk controls", "status": "review", "detail": "Position sizing is guarded, but fees and slippage are not yet modeled."},
            {"label": "Live deployment", "status": "review", "detail": "Use paper trading before real capital."},
        ],
        "notes": notes,
    }


def builder_run_output_fallback(
    name: str,
    code: str,
    author: Optional[str],
    summary: str,
    ticker: str,
    source: str,
) -> Dict[str, Any]:
    seed_text = f"{name}\n{summary}\n{code}\n{ticker}"
    series = build_model_series(seed_text)
    stats = {
        "annual_return": f"{8 + hash_slice(seed_text, 1) % 15:.1f}%",
        "benchmark_return": f"{5 + hash_slice(seed_text, 2) % 11:.1f}%",
        "sharpe": f"{0.8 + (hash_slice(seed_text, 3) % 85) / 100:.2f}",
        "max_drawdown": f"-{6 + hash_slice(seed_text, 4) % 16:.1f}%",
        "turnover": f"{18 + hash_slice(seed_text, 5) % 52:.1f}%",
        "win_rate": f"{45 + hash_slice(seed_text, 6) % 22:.1f}%",
    }
    profile = build_model_profile(name, summary, ["builder"], code)
    profile.update({"benchmark": ticker, "data_source": source, "data_window": "fallback simulation"})
    return {
        "name": clean_text(name),
        "author": clean_text(author or "Private workspace"),
        "summary": clean_text(summary or f"{name} generated a fallback simulation for {ticker}."),
        "ticker": ticker,
        "stats": stats,
        "profile": profile,
        "status": build_model_status(stats),
        "series": series,
        "highlights": build_model_highlights(stats, profile),
        "validation": [
            {"label": "Ticker data", "status": "review", "detail": "Live history was unavailable, so QFin used a deterministic fallback."},
            {"label": "Strategy parser", "status": "pass", "detail": "Model text was mapped to a guarded simulation template."},
            {"label": "Live deployment", "status": "review", "detail": "Do not use fallback results for trading decisions."},
        ],
        "notes": ["Fallback simulation generated because live market history was unavailable."],
    }


def builder_run_output(name: str, code: str, author: Optional[str], summary: Optional[str] = None, ticker: Optional[str] = None) -> Dict[str, Any]:
    clean_summary = clean_text(summary or "")
    resolved_ticker = resolve_builder_ticker(name, clean_summary, code, ticker)
    return run_builder_backtest(name, code, author, clean_summary, resolved_ticker)


def model_supabase_rows(model: Dict[str, Any], visibility: str) -> List[Dict[str, Any]]:
    base = {
        "name": model["name"],
        "author": model["author"],
        "summary": model["summary"],
        "code": model["code"],
        "tags": model["tags"],
        "stats": model["stats"],
        "score": model["score"],
        "visibility": visibility,
        "created_at": model["created_at"],
        "updated_at": utc_now(),
    }
    extended = {
        **base,
        "ticker": model.get("ticker"),
        "profile": model.get("profile") or {},
        "series": model.get("series") or [],
        "highlights": model.get("highlights") or [],
        "status": model.get("status") or "research",
        "last_run_result": model.get("last_run_result") or {},
    }
    return [extended, base]


def create_community_model_record(payload: BuilderPublishRequest) -> Dict[str, Any]:
    result = builder_run_output(payload.name, payload.code, payload.author, payload.summary, payload.ticker)
    model = {
        **result,
        "id": make_id("model"),
        "code": payload.code,
        "tags": ["community", "published", strategy_family(payload.name, payload.summary or "", payload.code)],
        "score": 1,
        "visibility": "public",
        "created_at": utc_now(),
        "last_run_result": result,
    }

    if supabase_is_configured():
        for row in model_supabase_rows(model, "public"):
            try:
                rows = supabase_request("POST", SUPABASE_MODEL_TABLE, json_body=row, prefer="return=representation") or []
                saved = normalize_model_record(rows[0] if isinstance(rows, list) else rows)
                return {"model": saved, "storage": "supabase"}
            except Exception:
                continue

    COMMUNITY_MODELS.insert(0, model)
    return {"model": model, "storage": "memory"}


def save_private_model_record(payload: BuilderPublishRequest) -> Dict[str, Any]:
    result = builder_run_output(payload.name, payload.code, payload.author, payload.summary, payload.ticker)
    record = {
        **result,
        "id": make_id("private_model"),
        "code": payload.code,
        "tags": ["private", strategy_family(payload.name, payload.summary or "", payload.code)],
        "score": 0,
        "visibility": "private",
        "created_at": utc_now(),
        "last_run_result": result,
    }

    if supabase_is_configured():
        for row in model_supabase_rows(record, "private"):
            try:
                rows = supabase_request("POST", SUPABASE_MODEL_TABLE, json_body=row, prefer="return=representation") or []
                saved = normalize_model_record(rows[0] if isinstance(rows, list) else rows)
                return {"model": saved, "storage": "supabase"}
            except Exception:
                continue

    PRIVATE_MODELS.insert(0, record)
    return {"model": record, "storage": "memory"}


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
        "api_registry": f"{base}/agent/api-registry",
        "symbol_resolve": f"{base}/symbols/resolve?query=Microsoft",
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "qfin-terminal-api",
        "version": "qfin-agent-2.6",
        "qwen_configured": qwen_is_configured(),
        "supabase_configured": supabase_is_configured(),
        "symbol_master_table": SUPABASE_SYMBOL_TABLE,
        "public_api_registry": "enabled",
        "agent_runtime": "router-evidence-risk-v1",
        "recent_agent_sessions": len(AGENT_SESSION_LOGS),
    }


@app.get("/agent/api-registry")
def agent_api_registry():
    return list_public_api_registry()


@app.get("/agent/sessions/recent")
def agent_recent_sessions():
    return {"sessions": AGENT_SESSION_LOGS[:10], "count": len(AGENT_SESSION_LOGS)}


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
    except Exception as exc:
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


@app.get("/symbols/resolve")
def resolve_symbol_master_route(query: str, symbol: Optional[str] = None):
    resolved = resolve_single_ticker(query, symbol)
    cached = SYMBOL_MASTER_CACHE.get(f"{symbol or ''}|{normalize_user_text(query)}") or {}
    return {
        "query": query,
        "symbol": resolved,
        "ticker": resolved,
        "status": "resolved" if resolved else "not_found",
        "source": "symbol_master" if cached else "resolver",
        "record": cached.get("record"),
    }


@app.post("/symbols/seed")
def seed_symbol_master_route():
    ensure_supabase_symbol_master_seeded()
    return {
        "status": "ok",
        "table": SUPABASE_SYMBOL_TABLE,
        "seed_count": len(default_symbol_master_records()),
        "supabase_configured": supabase_is_configured(),
    }


@app.get("/market-data/{ticker}")
def market_data_route(ticker: str):
    return get_cached_financial_data(ticker.strip().upper()) or fetch_financial_data(ticker.strip().upper())


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
    result = builder_run_output(payload.name, payload.code, payload.author, payload.summary, payload.ticker)
    return {"status": "ok", "result": result}


@app.post("/builder/save-private")
def builder_save_private(payload: BuilderPublishRequest):
    saved = save_private_model_record(payload)
    return {"status": "saved", "model": saved["model"], "storage": saved["storage"]}


@app.post("/builder/run-private")
def builder_run_private(payload: BuilderPublishRequest):
    saved = save_private_model_record(payload)
    result = builder_run_output(payload.name, payload.code, payload.author, payload.summary, payload.ticker)
    return {"status": "saved_and_ran", "model": saved["model"], "result": result, "storage": saved["storage"]}


@app.post("/builder/backtest")
def builder_backtest(payload: BuilderRunRequest):
    return builder_run(payload)


@app.post("/builder/publish")
def builder_publish(payload: BuilderPublishRequest):
    return create_community_model(payload)

