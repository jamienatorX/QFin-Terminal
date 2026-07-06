import os
import re
import xml.etree.ElementTree as ET
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
            return parsedate_to_datetime(value).timestamp()
    except Exception:
        return 0.0
    return 0.0

def _dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    output = []
    for item in items:
        title = str(item.get("title") or "").strip()
        link = str(item.get("link") or "").strip()
        key = (re.sub(r"\W+", "", title.lower())[:90], link)
        if not title or key in seen:
            continue
        seen.add(key)
        output.append(item)
    output.sort(key=lambda x: _time_value(x.get("providerPublishTime")), reverse=True)
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
                if category == "Other" or any(k in text for k in keys[:6]):
                    output.append({"title": title, "summary": desc, "publisher": source, "link": node.findtext("link"), "providerPublishTime": node.findtext("pubDate"), "source": f"{source} RSS"})
        except Exception:
            continue
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

async def fetch_all_sources(category: str) -> List[Dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0 QFinTerminal/1.0"}
    async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=headers) as client:
        items = []
        items.extend(await fetch_yahoo(client, category))
        items.extend(await fetch_gdelt(client, category))
        items.extend(await fetch_rss(client, category))
        items.extend(await fetch_newsapi(client, category))
    return _dedupe(items)
