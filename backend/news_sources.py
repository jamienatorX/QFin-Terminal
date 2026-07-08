import asyncio
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List
from urllib.parse import quote_plus

import httpx

CATEGORY_QUERIES = {
    "Crypto": "crypto bitcoin ethereum ETF regulation market",
    "Stocks": "stock market earnings federal reserve major indexes",
    "Bonds": "bond market treasury yields interest rates credit spreads",
    "ETFs": "ETF inflows outflows fund market sector ETF",
    "Other": "global markets commodities currencies macro economy",
}

CATEGORY_KEYWORDS = {
    "Crypto": [
        "crypto", "cryptocurrency", "bitcoin", "btc", "ethereum", "ether",
        "solana", "xrp", "token", "stablecoin", "blockchain", "defi", "web3",
    ],
    "Stocks": [
        "stock", "stocks", "share", "shares", "equity", "equities", "earnings",
        "guidance", "dividend", "buyback", "ipo", "valuation", "nasdaq", "nyse",
        "s&p", "dow", "index", "indices", "company", "quarter", "revenue",
    ],
    "Bonds": [
        "bond", "bonds", "treasury", "treasuries", "yield", "yields", "coupon",
        "fixed income", "credit spread", "spread", "municipal", "muni",
        "sovereign debt", "debt sale", "auction", "notes", "gilts",
    ],
    "ETFs": [
        "etf", "etfs", "exchange-traded fund", "fund flows", "inflows",
        "outflows", "ishares", "vanguard", "spdr", "invesco", "ark", "blackrock",
    ],
    "Other": [
        "commodity", "commodities", "oil", "crude", "gold", "silver", "copper",
        "natural gas", "forex", "fx", "currency", "currencies", "dollar", "usd",
        "euro", "yen", "yuan", "macro", "economy", "inflation", "cpi", "ppi",
        "jobs", "payrolls", "gdp", "central bank", "opec",
    ],
}

RSS_FEEDS = {
    "CNBC": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
}

def _time_value(value: Any) -> float:
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and value:
            if value.isdigit():
                return float(value)
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return parsedate_to_datetime(value).timestamp()
    except Exception:
        return 0.0
    return 0.0


def _category_score(item: Dict[str, Any], category: str) -> int:
    text = " ".join(
        str(item.get(field) or "")
        for field in ("title", "summary", "publisher", "link", "source")
    ).lower()
    score = 0
    for keyword in CATEGORY_KEYWORDS.get(category, []):
        if keyword in text:
            score += 2 if " " in keyword else 1
    if category == "Stocks":
        if any(token in text for token in ("shares", "earnings", "nasdaq", "nyse", "s&p", "dow")):
            score += 2
    return score


def _is_recent(item: Dict[str, Any]) -> bool:
    published_ts = _time_value(item.get("providerPublishTime"))
    if not published_ts:
        return True
    age = datetime.now(timezone.utc).timestamp() - published_ts
    return age <= timedelta(hours=36).total_seconds()


def _dedupe(items: List[Dict[str, Any]], category: str) -> List[Dict[str, Any]]:
    seen = set()
    output = []
    for item in items:
        title = str(item.get("title") or "").strip()
        link = str(item.get("link") or "").strip()
        key = (re.sub(r"\W+", "", title.lower())[:90], link)
        if not title or key in seen:
            continue
        score = _category_score(item, category)
        if score <= 0:
            continue
        if not _is_recent(item):
            continue
        seen.add(key)
        item["_category_score"] = score
        output.append(item)
    output.sort(key=lambda x: (x.get("_category_score", 0), _time_value(x.get("providerPublishTime"))), reverse=True)
    return output[:40]

async def fetch_yahoo(client: httpx.AsyncClient, category: str) -> List[Dict[str, Any]]:
    q = CATEGORY_QUERIES.get(category, CATEGORY_QUERIES["Stocks"])
    try:
        r = await client.get("https://query2.finance.yahoo.com/v1/finance/search", params={"q": q, "quotesCount": 0, "newsCount": 12})
        if r.status_code >= 400:
            return []
        return [{"title": x.get("title"), "summary": x.get("summary"), "publisher": x.get("publisher"), "link": x.get("link"), "providerPublishTime": x.get("providerPublishTime"), "source": "Yahoo Finance"} for x in r.json().get("news", [])]
    except Exception:
        return []

async def fetch_gdelt(client: httpx.AsyncClient, category: str) -> List[Dict[str, Any]]:
    q = quote_plus(CATEGORY_QUERIES.get(category, CATEGORY_QUERIES["Stocks"]))
    try:
        r = await client.get(f"https://api.gdeltproject.org/api/v2/doc/doc?query={q}&mode=ArtList&format=json&maxrecords=12&sort=HybridRel")
        if r.status_code >= 400:
            return []
        return [{"title": x.get("title"), "summary": x.get("domain"), "publisher": x.get("domain") or "GDELT", "link": x.get("url"), "providerPublishTime": x.get("seendate"), "source": "GDELT"} for x in r.json().get("articles", [])]
    except Exception:
        return []

async def fetch_rss(client: httpx.AsyncClient, category: str) -> List[Dict[str, Any]]:
    keys = CATEGORY_QUERIES.get(category, "markets").lower().split()
    output = []
    for source, url in RSS_FEEDS.items():
        try:
            r = await client.get(url)
            if r.status_code >= 400:
                continue
            root = ET.fromstring(r.text)
            for node in root.findall(".//item")[:12]:
                title = node.findtext("title") or ""
                desc = re.sub(r"<[^>]+>", "", node.findtext("description") or "").strip()
                text = f"{title} {desc}".lower()
                if category in {"Stocks", "Other"} or any(k in text for k in keys[:6]):
                    output.append({"title": title, "summary": desc, "publisher": source, "link": node.findtext("link"), "providerPublishTime": node.findtext("pubDate"), "source": f"{source} RSS"})
        except Exception:
            continue
    return output


async def fetch_google_news(client: httpx.AsyncClient, category: str) -> List[Dict[str, Any]]:
    query = quote_plus(CATEGORY_QUERIES.get(category, CATEGORY_QUERIES["Stocks"]))
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    output = []
    try:
        r = await client.get(url)
        if r.status_code >= 400:
            return []
        root = ET.fromstring(r.text)
        for node in root.findall(".//item")[:12]:
            title = node.findtext("title") or ""
            link = node.findtext("link")
            pub_date = node.findtext("pubDate")
            output.append(
                {
                    "title": title,
                    "summary": title,
                    "publisher": "Google News",
                    "link": link,
                    "providerPublishTime": pub_date,
                    "source": "Google News RSS",
                }
            )
    except Exception:
        return []
    return output

async def fetch_newsapi(client: httpx.AsyncClient, category: str) -> List[Dict[str, Any]]:
    key = os.getenv("NEWSAPI_KEY") or os.getenv("NEWS_API_KEY")
    if not key:
        return []
    q = CATEGORY_QUERIES.get(category, CATEGORY_QUERIES["Stocks"])
    try:
        r = await client.get("https://newsapi.org/v2/everything", params={"q": q, "language": "en", "sortBy": "publishedAt", "pageSize": 12, "apiKey": key})
        if r.status_code >= 400:
            return []
        return [{"title": x.get("title"), "summary": x.get("description"), "publisher": (x.get("source") or {}).get("name") or "NewsAPI", "link": x.get("url"), "providerPublishTime": x.get("publishedAt"), "source": "NewsAPI"} for x in r.json().get("articles", [])]
    except Exception:
        return []

async def fetch_finnhub(client: httpx.AsyncClient, category: str) -> List[Dict[str, Any]]:
    key = os.getenv("FINNHUB_API_KEY")
    if not key:
        return []
    finnhub_category = "crypto" if category == "Crypto" else "general"
    try:
        r = await client.get("https://finnhub.io/api/v1/news", params={"category": finnhub_category, "token": key})
        if r.status_code >= 400:
            return []
        return [{"title": x.get("headline"), "summary": x.get("summary"), "publisher": x.get("source") or "Finnhub", "link": x.get("url"), "providerPublishTime": x.get("datetime"), "source": "Finnhub"} for x in r.json()[:12]]
    except Exception:
        return []

async def fetch_all_sources(category: str) -> List[Dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0 QFinTerminal/1.0"}
    async with httpx.AsyncClient(timeout=6, follow_redirects=True, headers=headers) as client:
        items = []
        tasks = [
            fetch_yahoo(client, category),
            fetch_gdelt(client, category),
            fetch_rss(client, category),
            fetch_google_news(client, category),
            fetch_newsapi(client, category),
            fetch_finnhub(client, category),
        ]
        results = await asyncio.gather(
            *(asyncio.wait_for(task, timeout=7) for task in tasks),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, list):
                items.extend(result)
    return _dedupe(items, category)
