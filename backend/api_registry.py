from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import httpx


PUBLIC_API_REGISTRY: List[Dict[str, Any]] = [
    {
        "name": "Yahoo Finance via yfinance",
        "domain": "finance",
        "auth": "none",
        "purpose": "Global public-company prices, profiles, financial statements, and chart history.",
        "qfin_use": "Primary fallback for company analysis, comparisons, and model-builder backtests.",
        "status": "active",
    },
    {
        "name": "Finnhub",
        "domain": "finance",
        "auth": "apiKey",
        "purpose": "Market data, company fundamentals, earnings, and news enrichment.",
        "qfin_use": "Premium finance enrichment when FINNHUB_API_KEY is configured.",
        "status": "active",
    },
    {
        "name": "GDELT",
        "domain": "news",
        "auth": "none",
        "purpose": "Global news discovery and event monitoring.",
        "qfin_use": "Market-news source discovery by asset category and region.",
        "status": "candidate",
    },
    {
        "name": "Wikipedia REST API",
        "domain": "knowledge",
        "auth": "none",
        "purpose": "Encyclopedic summaries for people, companies, places, concepts, and events.",
        "qfin_use": "General question grounding when the user asks for a factual explanation.",
        "status": "active",
    },
    {
        "name": "REST Countries",
        "domain": "open-data",
        "auth": "none",
        "purpose": "Country, capital, population, currency, region, and flag metadata.",
        "qfin_use": "Country and macro-context questions.",
        "status": "active",
    },
    {
        "name": "Open-Meteo",
        "domain": "weather",
        "auth": "none",
        "purpose": "Geocoding plus weather forecast data.",
        "qfin_use": "Weather and temperature questions without requiring an API key.",
        "status": "active",
    },
    {
        "name": "Open Library",
        "domain": "books",
        "auth": "none",
        "purpose": "Book, author, publication, and ISBN search.",
        "qfin_use": "Book and author lookup questions.",
        "status": "active",
    },
    {
        "name": "World Bank Indicators",
        "domain": "macro",
        "auth": "none",
        "purpose": "Country-level macroeconomic indicators.",
        "qfin_use": "Future macro dashboard and country comparison enrichment.",
        "status": "candidate",
    },
    {
        "name": "SEC EDGAR",
        "domain": "finance",
        "auth": "none",
        "purpose": "US company filings and XBRL facts.",
        "qfin_use": "Future source-of-truth reports for US public companies.",
        "status": "candidate",
    },
    {
        "name": "FRED",
        "domain": "macro",
        "auth": "apiKey",
        "purpose": "US economic time series including rates, inflation, employment, and GDP.",
        "qfin_use": "Future macro and rates analysis.",
        "status": "candidate",
    },
]

PUBLIC_API_DOMAINS = [
    "animals",
    "anime",
    "anti-malware",
    "art-design",
    "auth",
    "blockchain",
    "books",
    "business",
    "calendar",
    "cloud-storage",
    "crypto",
    "currency-exchange",
    "development",
    "dictionaries",
    "documents",
    "email",
    "entertainment",
    "environment",
    "events",
    "finance",
    "food-drink",
    "games",
    "geocoding",
    "government",
    "health",
    "jobs",
    "machine-learning",
    "music",
    "news",
    "open-data",
    "open-source",
    "patent",
    "personality",
    "phone",
    "photography",
    "programming",
    "science-math",
    "security",
    "shopping",
    "social",
    "sports",
    "test-data",
    "text-analysis",
    "tracking",
    "transportation",
    "url-shorteners",
    "vehicle",
    "video",
    "weather",
]


def list_public_api_registry() -> Dict[str, Any]:
    return {
        "strategy": "Curated registry from public-apis style categories. QFin only activates reliable no-key tools by default.",
        "active_tools": [item for item in PUBLIC_API_REGISTRY if item["status"] == "active"],
        "candidate_tools": [item for item in PUBLIC_API_REGISTRY if item["status"] == "candidate"],
        "known_public_api_domains": PUBLIC_API_DOMAINS,
    }


def _trim_query(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" ?.!")


def _extract_after_marker(text: str, markers: List[str]) -> Optional[str]:
    lowered = text.lower()
    for marker in markers:
        index = lowered.rfind(marker)
        if index >= 0:
            candidate = text[index + len(marker):]
            candidate = re.split(r"[?.!,;]", candidate)[0]
            candidate = _trim_query(candidate)
            if candidate:
                return candidate
    return None


def _source(name: str, url: str, data: Any) -> Dict[str, Any]:
    return {"source": name, "url": url, "data": data}


async def _get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=3.0), follow_redirects=True) as client:
        response = await client.get(url, params=params, headers={"User-Agent": "QFin-Terminal/1.0"})
        response.raise_for_status()
        return response.json()


async def _wikipedia_summary(query: str) -> Optional[Dict[str, Any]]:
    if not re.search(r"\b(who|what|where|when|tell me about|explain)\b", query, re.I):
        return None
    search_url = "https://en.wikipedia.org/w/api.php"
    search = await _get_json(
        search_url,
        {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": 1,
        },
    )
    results = search.get("query", {}).get("search", [])
    if not results:
        return None
    title = results[0]["title"]
    summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}"
    summary = await _get_json(summary_url)
    return _source("Wikipedia REST API", summary_url, {
        "title": summary.get("title"),
        "description": summary.get("description"),
        "extract": summary.get("extract"),
    })


async def _country_lookup(query: str) -> Optional[Dict[str, Any]]:
    if not re.search(r"\b(country|capital|population|currency|timezone|region)\b", query, re.I):
        return None
    country = _extract_after_marker(query, [" of ", " in ", " about ", " for "]) or query
    country = re.sub(r"\b(country|capital|population|currency|timezone|region|what|is|the|of|in|for)\b", " ", country, flags=re.I)
    country = _trim_query(country)
    if len(country) < 2:
        return None
    url = f"https://restcountries.com/v3.1/name/{country}"
    rows = await _get_json(url, {"fields": "name,capital,population,currencies,region,subregion,timezones,flags"})
    if not rows:
        return None
    row = rows[0]
    return _source("REST Countries", url, {
        "name": row.get("name", {}).get("common"),
        "official_name": row.get("name", {}).get("official"),
        "capital": row.get("capital"),
        "population": row.get("population"),
        "currencies": row.get("currencies"),
        "region": row.get("region"),
        "subregion": row.get("subregion"),
        "timezones": row.get("timezones"),
    })


async def _weather_lookup(query: str) -> Optional[Dict[str, Any]]:
    if not re.search(r"\b(weather|temperature|forecast|rain|wind)\b", query, re.I):
        return None
    location = _extract_after_marker(query, [" in ", " at ", " for "])
    if not location:
        return None
    geocode_url = "https://geocoding-api.open-meteo.com/v1/search"
    geocode = await _get_json(geocode_url, {"name": location, "count": 1, "language": "en", "format": "json"})
    results = geocode.get("results", [])
    if not results:
        return None
    place = results[0]
    forecast_url = "https://api.open-meteo.com/v1/forecast"
    forecast = await _get_json(
        forecast_url,
        {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation",
            "timezone": "auto",
        },
    )
    return _source("Open-Meteo", forecast_url, {
        "location": {
            "name": place.get("name"),
            "country": place.get("country"),
            "timezone": place.get("timezone"),
        },
        "current": forecast.get("current"),
        "units": forecast.get("current_units"),
    })


async def _book_lookup(query: str) -> Optional[Dict[str, Any]]:
    if not re.search(r"\b(book|author|novel|isbn|publication)\b", query, re.I):
        return None
    url = "https://openlibrary.org/search.json"
    data = await _get_json(url, {"q": query, "limit": 3})
    docs = data.get("docs", [])[:3]
    if not docs:
        return None
    return _source("Open Library", url, [
        {
            "title": item.get("title"),
            "author_name": item.get("author_name", [])[:3],
            "first_publish_year": item.get("first_publish_year"),
            "isbn": item.get("isbn", [])[:3],
        }
        for item in docs
    ])


async def fetch_public_api_facts(query: str) -> Dict[str, Any]:
    facts: List[Dict[str, Any]] = []
    errors: List[str] = []
    for fetcher in (_weather_lookup, _country_lookup, _book_lookup, _wikipedia_summary):
        try:
            result = await fetcher(query)
            if result:
                facts.append(result)
        except Exception as exc:
            errors.append(f"{fetcher.__name__}: {type(exc).__name__}")
    return {
        "query": query,
        "facts": facts,
        "errors": errors,
        "registry_hint": "Only active, no-key public data APIs are used for automatic enrichment.",
    }
