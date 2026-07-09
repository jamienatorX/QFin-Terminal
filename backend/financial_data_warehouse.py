from __future__ import annotations

import html
import os
import re
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx


FMP_BASE_URL = "https://financialmodelingprep.com/stable"
FMP_TIMEOUT = httpx.Timeout(20.0, connect=5.0)
FMP_USER_AGENT = "QFin-Terminal/1.0"
SOURCE_CONFIDENCE = 0.70
ANNUAL_REPORT_TIMEOUT = httpx.Timeout(25.0, connect=8.0)
MAX_ANNUAL_REPORT_BYTES = 18_000_000
MAX_REPORT_TEXT_CHARS = 12_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def fmp_is_configured() -> bool:
    return bool(os.getenv("FMP_API_KEY"))


def _clean_symbol(value: str) -> str:
    return (value or "").strip().upper()


def _symbol_candidates(symbol: str) -> List[str]:
    cleaned = _clean_symbol(symbol)
    if not cleaned:
        return []
    candidates = [cleaned]
    if "." in cleaned:
        candidates.append(cleaned.split(".", 1)[0])
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _host(value: str) -> str:
    try:
        return urlparse(value).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _base_url(value: str) -> str:
    parsed = urlparse(value or "")
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _is_pdf_url(url: str) -> bool:
    lowered = url.lower().split("?", 1)[0]
    return lowered.endswith(".pdf") or "/pdf" in lowered or "format=pdf" in url.lower()


def _annual_report_score(url: str, title: str = "") -> int:
    text = f"{url} {title}".lower()
    score = 0
    for token in ["annual-report", "annual report", "laporan-tahunan", "laporan tahunan", "annual_report"]:
        if token in text:
            score += 40
    if ".pdf" in text:
        score += 30
    if "financial" in text or "keuangan" in text:
        score += 8
    years = re.findall(r"20\d{2}", text)
    if years:
        score += max(int(year) for year in years) - 2000
    if any(bad in text for bad in ["quarter", "quarterly", "press-release", "newsletter", "privacy", "prospectus"]):
        score -= 15
    return score


def _normalize_search_url(href: str) -> str:
    href = html.unescape(href or "")
    if not href:
        return ""
    if href.startswith("//"):
        href = f"https:{href}"
    if href.startswith("/l/?") or "duckduckgo.com/l/?" in href:
        parsed = urlparse(href)
        params = parse_qs(parsed.query)
        target = params.get("uddg", [""])[0]
        if target:
            return unquote(target)
    return href


def _extract_links(html_text: str, base_url: str = "") -> List[Dict[str, str]]:
    links: List[Dict[str, str]] = []
    pattern = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
    for href, label in pattern.findall(html_text or ""):
        normalized = _normalize_search_url(href)
        if base_url:
            normalized = urljoin(base_url, normalized)
        normalized = normalized.strip()
        if not normalized.startswith(("http://", "https://")):
            continue
        clean_label = re.sub(r"<[^>]+>", " ", label)
        clean_label = re.sub(r"\s+", " ", html.unescape(clean_label)).strip()
        links.append({"url": normalized, "title": clean_label})
    return links


async def _download_text(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(url, headers={"User-Agent": FMP_USER_AGENT})
    response.raise_for_status()
    return response.text


async def _download_bytes(client: httpx.AsyncClient, url: str, max_bytes: int = MAX_ANNUAL_REPORT_BYTES) -> bytes:
    response = await client.get(url, headers={"User-Agent": FMP_USER_AGENT})
    response.raise_for_status()
    data = response.content
    if len(data) > max_bytes:
        raise RuntimeError("annual report PDF is larger than the configured limit")
    return data


def _extract_pdf_text(pdf_bytes: bytes, max_pages: int = 12) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        chunks: List[str] = []
        for page in reader.pages[:max_pages]:
            page_text = page.extract_text() or ""
            if page_text.strip():
                chunks.append(page_text)
            if sum(len(chunk) for chunk in chunks) >= MAX_REPORT_TEXT_CHARS:
                break
        text = "\n".join(chunks)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:MAX_REPORT_TEXT_CHARS]
    except Exception:
        return ""


async def _search_duckduckgo(client: httpx.AsyncClient, query: str) -> List[Dict[str, str]]:
    try:
        response = await client.get(
            "https://duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": FMP_USER_AGENT},
        )
        response.raise_for_status()
        return _extract_links(response.text, "https://duckduckgo.com")
    except Exception:
        return []


async def _official_site_candidates(client: httpx.AsyncClient, website: str) -> List[Dict[str, str]]:
    base = _base_url(website)
    if not base:
        return []

    paths = [
        "/",
        "/en/about-bca/investor-relations/annual-report",
        "/id/tentang-bca/hubungan-investor/laporan-tahunan",
        "/en/about-bca/investor-relations",
        "/id/tentang-bca/hubungan-investor",
        "/investor-relations/annual-report",
        "/investor-relations/reports",
        "/annual-report",
        "/laporan-tahunan",
    ]
    found: List[Dict[str, str]] = []
    for path in paths:
        page_url = urljoin(base, path)
        try:
            page_html = await _download_text(client, page_url)
        except Exception:
            continue
        for link in _extract_links(page_html, page_url):
            text = f"{link.get('url', '')} {link.get('title', '')}".lower()
            if any(token in text for token in ["annual", "laporan", "report", ".pdf"]):
                found.append(link)
    return found


async def discover_annual_report(company_name: str, symbol: str, website: Optional[str] = None) -> Optional[Dict[str, Any]]:
    company_name = (company_name or "").strip()
    symbol = _clean_symbol(symbol)
    website = website or ""
    trusted_host = _host(website)
    base_symbol = symbol.split(".", 1)[0]

    search_queries = [
        f'"{company_name}" "annual report" pdf',
        f'"{company_name}" "laporan tahunan" pdf',
        f'"{symbol}" "annual report" pdf',
        f'"{base_symbol}" "laporan tahunan" pdf',
    ]

    async with httpx.AsyncClient(timeout=ANNUAL_REPORT_TIMEOUT, follow_redirects=True) as client:
        candidates: List[Dict[str, str]] = []
        candidates.extend(await _official_site_candidates(client, website))
        for query in search_queries:
            candidates.extend(await _search_duckduckgo(client, query))

        deduped: Dict[str, Dict[str, str]] = {}
        for item in candidates:
            url = item.get("url", "")
            title = item.get("title", "")
            if not url.startswith(("http://", "https://")):
                continue
            url_host = _host(url)
            trusted = bool(trusted_host and trusted_host in url_host) or any(host in url_host for host in ["idx.co.id", "bca.co.id"])
            if not trusted and symbol.endswith(".JK"):
                continue
            if _annual_report_score(url, title) <= 20:
                continue
            deduped[url] = {"url": url, "title": title}

        ranked = sorted(deduped.values(), key=lambda item: _annual_report_score(item["url"], item.get("title", "")), reverse=True)

        pdf_candidates: List[Dict[str, str]] = []
        for item in ranked[:15]:
            url = item["url"]
            if _is_pdf_url(url):
                pdf_candidates.append(item)
                continue
            try:
                page_html = await _download_text(client, url)
                for link in _extract_links(page_html, url):
                    if _is_pdf_url(link.get("url", "")) and _annual_report_score(link.get("url", ""), link.get("title", "")) > 20:
                        pdf_candidates.append(link)
            except Exception:
                continue

        pdf_deduped: Dict[str, Dict[str, str]] = {item["url"]: item for item in pdf_candidates if item.get("url")}
        pdf_ranked = sorted(pdf_deduped.values(), key=lambda item: _annual_report_score(item["url"], item.get("title", "")), reverse=True)

        for item in pdf_ranked[:8]:
            pdf_url = item["url"]
            try:
                pdf_bytes = await _download_bytes(client, pdf_url)
                text_excerpt = _extract_pdf_text(pdf_bytes)
                years = re.findall(r"20\d{2}", f"{item.get('title', '')} {pdf_url} {text_excerpt[:500]}")
                report_year = max([int(year) for year in years], default=None)
                return {
                    "status": "found",
                    "symbol": symbol,
                    "company_name": company_name,
                    "report_year": report_year,
                    "report_type": "annual_report",
                    "source_url": pdf_url,
                    "source_title": item.get("title") or "Annual report PDF",
                    "source_host": _host(pdf_url),
                    "source_confidence": SOURCE_CONFIDENCE,
                    "downloaded_at": utc_now(),
                    "bytes": len(pdf_bytes),
                    "text_excerpt": text_excerpt,
                }
            except Exception:
                continue

    return {
        "status": "not_found",
        "symbol": symbol,
        "company_name": company_name,
        "source_confidence": 0.0,
        "checked_at": utc_now(),
    }


async def _fmp_get(path: str, params: Optional[Dict[str, Any]] = None) -> Any:
    api_key = os.getenv("FMP_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("FMP_API_KEY is not configured.")

    query = dict(params or {})
    query["apikey"] = api_key

    async with httpx.AsyncClient(timeout=FMP_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(
            f"{FMP_BASE_URL}{path}",
            params=query,
            headers={"User-Agent": FMP_USER_AGENT},
        )
        response.raise_for_status()
        return response.json()


async def fetch_fmp_bundle(symbol: str, limit: int = 5) -> Dict[str, Any]:
    requested_symbol = _clean_symbol(symbol)
    endpoints = {
        "profile": ("/profile", {}),
        "income_statement": ("/income-statement", {"limit": limit, "period": "annual"}),
        "balance_sheet_statement": ("/balance-sheet-statement", {"limit": limit, "period": "annual"}),
        "cash_flow_statement": ("/cash-flow-statement", {"limit": limit, "period": "annual"}),
        "key_metrics": ("/key-metrics", {"limit": limit, "period": "annual"}),
        "ratios": ("/ratios", {"limit": limit, "period": "annual"}),
        "key_metrics_ttm": ("/key-metrics-ttm", {}),
        "ratios_ttm": ("/ratios-ttm", {}),
        "enterprise_values": ("/enterprise-values", {"limit": limit, "period": "annual"}),
    }

    warnings: List[str] = []
    endpoint_payloads: Dict[str, Any] = {}
    resolved_symbol = requested_symbol
    resolved_any = False

    for endpoint_name, (path, base_params) in endpoints.items():
        result = None
        last_error = None
        matched_symbol = None
        for candidate in _symbol_candidates(requested_symbol):
            params = {"symbol": candidate, **base_params}
            try:
                payload = await _fmp_get(path, params=params)
                if isinstance(payload, list) and payload:
                    result = payload
                    matched_symbol = candidate
                    break
                if isinstance(payload, dict) and payload:
                    result = payload
                    matched_symbol = candidate
                    break
            except Exception as exc:
                last_error = exc
        if matched_symbol:
            resolved_symbol = matched_symbol
            resolved_any = True
        elif last_error:
            warnings.append(f"{endpoint_name}: {type(last_error).__name__}")
        else:
            warnings.append(f"{endpoint_name}: no_data")
        endpoint_payloads[endpoint_name] = result

    profile = _first_list_row(endpoint_payloads.get("profile"))
    annual_report = None
    if profile:
        annual_report = await discover_annual_report(
            profile.get("companyName") or profile.get("name") or requested_symbol,
            requested_symbol,
            profile.get("website"),
        )
        endpoint_payloads["annual_report"] = annual_report
        if annual_report and annual_report.get("status") == "found":
            resolved_any = True
        elif annual_report:
            warnings.append("annual_report: not_found")

    status = "success" if resolved_any else "provider_gap"
    return {
        "provider": "fmp",
        "requested_symbol": requested_symbol,
        "resolved_symbol": resolved_symbol,
        "retrieved_at": utc_now(),
        "status": status,
        "warnings": warnings,
        "endpoints": endpoint_payloads,
    }


def _first_list_row(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, list) and payload:
        first = payload[0]
        return first if isinstance(first, dict) else {}
    return payload if isinstance(payload, dict) else {}


def _number(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        result = float(value)
        return None if result != result else result
    except Exception:
        return None


def _iso_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text[:10] if len(text) >= 10 else text or None


def _period_type(row: Dict[str, Any]) -> str:
    period = str(row.get("period") or "").strip().upper()
    if period in {"Q1", "Q2", "Q3", "Q4"}:
        return "quarterly"
    return "annual"


def _fiscal_period(row: Dict[str, Any]) -> str:
    period = str(row.get("period") or "").strip().upper()
    return period or "FY"


def _safe_fiscal_year(value: Any, fallback_date: Optional[str]) -> int:
    if value is not None and str(value).isdigit():
        return int(value)
    if fallback_date and len(fallback_date) >= 4 and fallback_date[:4].isdigit():
        return int(fallback_date[:4])
    return datetime.now(timezone.utc).year


def _metric_unit(statement_type: str, metric_name: str) -> str:
    lowered = metric_name.lower()
    if statement_type == "ratios" or "ratio" in lowered or "margin" in lowered or "yield" in lowered or "returnon" in lowered:
        return "ratio"
    if "shares" in lowered or "employees" in lowered:
        return "count"
    return "currency"


def normalize_profile(symbol: str, bundle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    endpoints = bundle.get("endpoints") or {}
    profile = _first_list_row(endpoints.get("profile"))
    if not profile:
        return None

    annual_report = endpoints.get("annual_report")
    provider_payload = {"profile": profile}
    if annual_report:
        provider_payload["annual_report"] = annual_report

    return {
        "symbol": _clean_symbol(symbol),
        "provider_symbol": _clean_symbol(str(profile.get("symbol") or bundle.get("resolved_symbol") or symbol)),
        "company_name": profile.get("companyName") or profile.get("companyNameLong") or profile.get("name") or _clean_symbol(symbol),
        "exchange": profile.get("exchange") or profile.get("exchangeShortName"),
        "market": profile.get("exchangeShortName") or profile.get("exchange"),
        "sector": profile.get("sector"),
        "industry": profile.get("industry"),
        "country": profile.get("country"),
        "currency": profile.get("currency"),
        "ipo_date": _iso_date(profile.get("ipoDate")),
        "website": profile.get("website"),
        "description": profile.get("description"),
        "provider_payload": provider_payload,
        "source": "fmp",
        "source_confidence": SOURCE_CONFIDENCE,
        "retrieved_at": bundle.get("retrieved_at") or utc_now(),
        "updated_at": utc_now(),
    }


def normalize_statement_rows(symbol: str, bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    endpoint_rows = bundle.get("endpoints") or {}
    source = "fmp"
    base_symbol = _clean_symbol(symbol)
    profile = _first_list_row(endpoint_rows.get("profile"))
    company_name = profile.get("companyName") or profile.get("name") or ""
    currency = profile.get("currency") or ""
    retrieved_at = bundle.get("retrieved_at") or utc_now()
    default_date = _iso_date(retrieved_at) or today_iso()
    statement_map = {
        "income_statement": "income_statement",
        "balance_sheet_statement": "balance_sheet",
        "cash_flow_statement": "cash_flow",
        "key_metrics": "key_metrics",
        "ratios": "ratios",
    }

    rows: List[Dict[str, Any]] = []
    for endpoint_name, statement_type in statement_map.items():
        payload = endpoint_rows.get(endpoint_name) or []
        if not isinstance(payload, list):
            continue
        for item in payload:
            if not isinstance(item, dict):
                continue
            report_date = _iso_date(item.get("date") or item.get("fillingDate")) or default_date
            accepted_date = _iso_date(item.get("acceptedDate")) or report_date
            fiscal_year = _safe_fiscal_year(item.get("calendarYear") or item.get("fiscalYear"), report_date)
            period_type = _period_type(item)
            fiscal_period = _fiscal_period(item)
            provider_symbol = _clean_symbol(str(item.get("symbol") or bundle.get("resolved_symbol") or symbol))
            for metric_name, metric_value in item.items():
                numeric_value = _number(metric_value)
                if numeric_value is None:
                    continue
                metric_key = str(metric_name)
                rows.append(
                    {
                        "symbol": base_symbol,
                        "provider_symbol": provider_symbol,
                        "company_name": company_name,
                        "fiscal_year": fiscal_year,
                        "fiscal_period": fiscal_period,
                        "period_type": period_type,
                        "period_end_date": report_date,
                        "statement_type": statement_type,
                        "metric_name": metric_key,
                        "metric_label": metric_key,
                        "metric_value": numeric_value,
                        "metric_unit": _metric_unit(statement_type, metric_key),
                        "currency": currency,
                        "source": source,
                        "source_url": "",
                        "source_confidence": SOURCE_CONFIDENCE,
                        "provider_payload": {},
                        "report_date": report_date,
                        "accepted_date": accepted_date,
                        "retrieved_at": retrieved_at,
                        "updated_at": utc_now(),
                    }
                )
    return rows


def calculate_valuation_snapshot(symbol: str, bundle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    endpoints = bundle.get("endpoints") or {}
    metrics_ttm = _first_list_row(endpoints.get("key_metrics_ttm"))
    ratios_ttm = _first_list_row(endpoints.get("ratios_ttm"))
    enterprise = _first_list_row(endpoints.get("enterprise_values"))
    if not metrics_ttm and not ratios_ttm and not enterprise:
        return None

    profile = _first_list_row(endpoints.get("profile"))
    snapshot_date = _iso_date(enterprise.get("date")) or _iso_date(bundle.get("retrieved_at")) or today_iso()
    fiscal_period = str(enterprise.get("period") or "TTM").upper()

    return {
        "symbol": _clean_symbol(symbol),
        "provider_symbol": _clean_symbol(str(profile.get("symbol") or bundle.get("resolved_symbol") or symbol)),
        "snapshot_date": snapshot_date,
        "fiscal_period": fiscal_period,
        "market_cap": _number(enterprise.get("marketCapitalization")),
        "enterprise_value": _number(enterprise.get("enterpriseValue")),
        "shares_outstanding": _number(enterprise.get("numberOfShares")),
        "pe_ratio": _number(ratios_ttm.get("priceEarningsRatioTTM")) or _number(ratios_ttm.get("priceEarningsRatio")),
        "pb_ratio": _number(ratios_ttm.get("priceToBookRatioTTM")) or _number(ratios_ttm.get("priceToBookRatio")),
        "ps_ratio": _number(ratios_ttm.get("priceToSalesRatioTTM")) or _number(ratios_ttm.get("priceToSalesRatio")),
        "ev_ebitda": _number(metrics_ttm.get("enterpriseValueOverEBITDATTM")) or _number(metrics_ttm.get("enterpriseValueOverEBITDA")),
        "dividend_yield": _number(ratios_ttm.get("dividendYieldTTM")) or _number(ratios_ttm.get("dividendYield")),
        "roe": _number(ratios_ttm.get("returnOnEquityTTM")) or _number(ratios_ttm.get("returnOnEquity")),
        "roa": _number(ratios_ttm.get("returnOnAssetsTTM")) or _number(ratios_ttm.get("returnOnAssets")),
        "data_quality": "ttm" if metrics_ttm or ratios_ttm else "annual_only",
        "source": "fmp",
        "source_confidence": SOURCE_CONFIDENCE,
        "retrieved_at": bundle.get("retrieved_at") or utc_now(),
        "updated_at": utc_now(),
    }


def _looks_like_bank(profile: Dict[str, Any]) -> bool:
    text = " ".join(
        str(profile.get(field) or "")
        for field in ["sector", "industry", "company_name", "description"]
    ).lower()
    return any(token in text for token in ["bank", "banc", "financial services", "lender"])


def calculate_bank_kpi_row(symbol: str, bundle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    profile = normalize_profile(symbol, bundle) or {}
    if not _looks_like_bank(profile):
        return None

    ratios = _first_list_row((bundle.get("endpoints") or {}).get("ratios"))
    metrics = _first_list_row((bundle.get("endpoints") or {}).get("key_metrics"))
    if not ratios and not metrics:
        return None

    fiscal_year = _safe_fiscal_year(ratios.get("calendarYear") or metrics.get("calendarYear"), _iso_date(ratios.get("date") or metrics.get("date")))
    fiscal_period = str(ratios.get("period") or metrics.get("period") or "FY").upper()
    period_type = "quarterly" if fiscal_period in {"Q1", "Q2", "Q3", "Q4"} else "annual"

    return {
        "symbol": _clean_symbol(symbol),
        "provider_symbol": _clean_symbol(str(profile.get("provider_symbol") or symbol)),
        "fiscal_year": fiscal_year,
        "fiscal_period": fiscal_period,
        "period_type": period_type,
        "return_on_assets": _number(ratios.get("returnOnAssets")),
        "return_on_equity": _number(ratios.get("returnOnEquity")),
        "debt_to_equity": _number(ratios.get("debtEquityRatio")),
        "price_to_book": _number(ratios.get("priceToBookRatio")),
        "tier1_proxy": _number(metrics.get("tangibleAssetValue")) or _number(metrics.get("netCurrentAssetValue")),
        "nim": None,
        "loan_to_deposit": None,
        "efficiency_ratio": None,
        "source": "fmp",
        "source_confidence": SOURCE_CONFIDENCE,
        "note": "FMP coverage for bank-specific KPIs is partial; blank fields indicate provider gaps.",
        "retrieved_at": bundle.get("retrieved_at") or utc_now(),
        "updated_at": utc_now(),
    }


def build_metric_coverage(
    symbol: str,
    years: List[int],
    statement_rows: List[Dict[str, Any]],
    valuation: Optional[Dict[str, Any]],
    bank_kpi: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    requirements = {
        "income_statement": {
            "revenue": {"revenue", "totalRevenue"},
            "net_income": {"netIncome", "netIncomeRatio"},
        },
        "balance_sheet": {
            "total_assets": {"totalAssets"},
            "total_equity": {"totalStockholdersEquity", "totalEquity"},
        },
        "cash_flow": {
            "operating_cash_flow": {"operatingCashFlow"},
            "free_cash_flow": {"freeCashFlow"},
        },
    }

    lookup = {
        (
            row.get("fiscal_year"),
            row.get("statement_type"),
            row.get("metric_name"),
        ): row
        for row in statement_rows
    }

    coverage_rows: List[Dict[str, Any]] = []
    now = utc_now()
    any_statement_data = bool(statement_rows)
    latest_year = years[0] if years else datetime.now(timezone.utc).year

    for year in years:
        for metric_group, metric_map in requirements.items():
            for metric_name, aliases in metric_map.items():
                matched = any(
                    lookup.get((year, metric_group, alias)) is not None
                    for alias in aliases
                )
                coverage_rows.append(
                    {
                        "symbol": _clean_symbol(symbol),
                        "fiscal_year": year,
                        "fiscal_period": "FY",
                        "metric_group": metric_group,
                        "metric_name": metric_name,
                        "status": "available" if matched else ("missing" if any_statement_data else "not_applicable"),
                        "note": "" if matched else "Provider did not return this metric for the selected symbol/year.",
                        "source": "fmp",
                        "source_confidence": SOURCE_CONFIDENCE,
                        "updated_at": now,
                    }
                )

    valuation_metrics = {
        "market_cap": valuation.get("market_cap") if valuation else None,
        "pe_ratio": valuation.get("pe_ratio") if valuation else None,
        "pb_ratio": valuation.get("pb_ratio") if valuation else None,
        "ps_ratio": valuation.get("ps_ratio") if valuation else None,
        "ev_ebitda": valuation.get("ev_ebitda") if valuation else None,
    }
    for metric_name, metric_value in valuation_metrics.items():
        coverage_rows.append(
            {
                "symbol": _clean_symbol(symbol),
                "fiscal_year": latest_year,
                "fiscal_period": "TTM",
                "metric_group": "valuation",
                "metric_name": metric_name,
                "status": "available" if metric_value is not None else ("missing" if valuation else "not_applicable"),
                "note": "" if metric_value is not None else "TTM valuation metric is unavailable from the provider.",
                "source": "fmp",
                "source_confidence": SOURCE_CONFIDENCE,
                "updated_at": now,
            }
        )

    if bank_kpi:
        for metric_name in [
            "return_on_assets",
            "return_on_equity",
            "debt_to_equity",
            "price_to_book",
            "tier1_proxy",
            "nim",
            "loan_to_deposit",
            "efficiency_ratio",
        ]:
            metric_value = bank_kpi.get(metric_name)
            coverage_rows.append(
                {
                    "symbol": _clean_symbol(symbol),
                    "fiscal_year": bank_kpi.get("fiscal_year") or latest_year,
                    "fiscal_period": bank_kpi.get("fiscal_period") or "FY",
                    "metric_group": "bank_kpi",
                    "metric_name": metric_name,
                    "status": "available" if metric_value is not None else "missing",
                    "note": "" if metric_value is not None else "Provider did not return this bank KPI.",
                    "source": "fmp",
                    "source_confidence": SOURCE_CONFIDENCE,
                    "updated_at": now,
                }
            )

    return coverage_rows
