from __future__ import annotations

import html
import os
import re
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx


FMP_BASE_URL = "https://financialmodelingprep.com/stable"
FMP_TIMEOUT = httpx.Timeout(20.0, connect=5.0)
FMP_USER_AGENT = "QFin-Terminal/1.0"
SOURCE_CONFIDENCE = 0.70
ANNUAL_REPORT_TIMEOUT = httpx.Timeout(25.0, connect=8.0)
MAX_ANNUAL_REPORT_BYTES = 18_000_000
MAX_REPORT_TEXT_CHARS = 70_000
MAX_TABLE_TEXT_CHARS = 80_000
GLOBAL_REPORT_HOSTS = {
    "annualreports.com",
    "sec.gov",
    "sedarplus.ca",
    "companieshouse.gov.uk",
    "asx.com.au",
    "jpx.co.jp",
    "hkexnews.hk",
    "sgx.com",
    "idx.co.id",
    "bursa-malaysia.com",
    "londonstockexchange.com",
    "euronext.com",
}


BANK_KPI_ALIASES = {
    "nim": ["net interest margin", "nim", "marjin bunga bersih"],
    "npl_ratio": ["non-performing loan", "non performing loan", "npl ratio", "gross npl", "rasio kredit bermasalah", "kredit bermasalah"],
    "casa_ratio": ["casa ratio", "casa", "current account saving account", "current account savings account", "giro dan tabungan"],
    "car": ["capital adequacy ratio", "car", "rasio kecukupan modal", "kewajiban penyediaan modal minimum", "kpm m", "kpmm"],
    "loan_to_deposit_ratio": ["loan to deposit ratio", "loan-to-deposit", "ldr", "loan deposit ratio", "rasio kredit terhadap dana pihak ketiga"],
    "cost_to_income_ratio": ["cost to income ratio", "cost-to-income", "cir", "efficiency ratio", "rasio biaya terhadap pendapatan", "cost/income"],
    "roe": ["return on equity", "roe", "imbal hasil ekuitas"],
    "roa": ["return on assets", "roa", "imbal hasil aset"],
    "total_assets": ["total assets", "jumlah aset", "total aset"],
    "total_equity": ["total equity", "total ekuitas", "jumlah ekuitas"],
    "total_loans": ["total loans", "loans", "loan portfolio", "kredit yang diberikan", "total kredit"],
    "customer_deposits": ["customer deposits", "total deposits", "third party funds", "dana pihak ketiga", "simpanan nasabah"],
    "net_interest_income": ["net interest income", "pendapatan bunga bersih"],
    "net_income": ["net income", "net profit", "profit for the year", "laba bersih", "laba tahun berjalan"],
}

RATIO_KPIS = {
    "nim",
    "npl_ratio",
    "casa_ratio",
    "car",
    "loan_to_deposit_ratio",
    "cost_to_income_ratio",
    "roe",
    "roa",
}


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


def _is_known_report_host(url: str) -> bool:
    host = _host(url)
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in GLOBAL_REPORT_HOSTS)


def _is_pdf_url(url: str) -> bool:
    lowered = url.lower().split("?", 1)[0]
    return lowered.endswith(".pdf") or "/pdf" in lowered or "format=pdf" in url.lower()


def _annual_report_score(url: str, title: str = "", official_host: str = "") -> int:
    text = f"{url} {title}".lower()
    host = _host(url)
    score = 0
    for token in ["annual-report", "annual report", "annual_report", "form-10-k", "10-k", "20-f", "laporan-tahunan", "laporan tahunan", "integrated-report", "integrated report"]:
        if token in text:
            score += 38
    if ".pdf" in text:
        score += 30
    if "financial" in text or "keuangan" in text or "investor" in text or "shareholder" in text:
        score += 10
    if official_host and official_host in host:
        score += 35
    if _is_known_report_host(url):
        score += 28
    years = re.findall(r"20\d{2}", text)
    if years:
        score += max(int(year) for year in years) - 2000
    if any(bad in text for bad in ["quarter", "quarterly", "press-release", "newsletter", "privacy", "prospectus", "sustainability-only"]):
        score -= 18
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


def _clean_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text).strip()


def _table_to_markdown_rows(table: List[List[Any]]) -> List[str]:
    rows: List[str] = []
    for row in table or []:
        clean = [_clean_cell(cell) for cell in row]
        if any(clean):
            rows.append(" | ".join(clean))
    return rows


def _extract_pdf_content(pdf_bytes: bytes, max_pages: int = 45) -> Dict[str, Any]:
    text_chunks: List[str] = []
    table_text_chunks: List[str] = []
    structured_tables: List[Dict[str, Any]] = []
    extraction_method = "none"

    try:
        import pdfplumber

        with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
            for page_number, page in enumerate(pdf.pages[:max_pages], start=1):
                try:
                    page_text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                    if page_text.strip():
                        text_chunks.append(page_text)
                except Exception:
                    pass

                try:
                    tables = page.extract_tables(
                        table_settings={
                            "vertical_strategy": "lines",
                            "horizontal_strategy": "lines",
                            "intersection_tolerance": 5,
                            "snap_tolerance": 3,
                            "join_tolerance": 3,
                            "edge_min_length": 3,
                        }
                    ) or []
                    if not tables:
                        tables = page.extract_tables(
                            table_settings={
                                "vertical_strategy": "text",
                                "horizontal_strategy": "text",
                                "intersection_tolerance": 5,
                                "snap_tolerance": 3,
                                "join_tolerance": 3,
                                "min_words_vertical": 2,
                                "min_words_horizontal": 1,
                            }
                        ) or []
                    for table_index, table in enumerate(tables, start=1):
                        rows = _table_to_markdown_rows(table)
                        if not rows:
                            continue
                        structured_tables.append(
                            {
                                "page": page_number,
                                "table_index": table_index,
                                "rows": rows[:80],
                            }
                        )
                        table_text_chunks.append(f"TABLE page={page_number} index={table_index}\n" + "\n".join(rows[:80]))
                except Exception:
                    pass

                if sum(len(chunk) for chunk in text_chunks) >= MAX_REPORT_TEXT_CHARS and sum(len(chunk) for chunk in table_text_chunks) >= MAX_TABLE_TEXT_CHARS:
                    break
        extraction_method = "pdfplumber_tables" if structured_tables else "pdfplumber_text"
    except Exception:
        pass

    if not text_chunks:
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(pdf_bytes))
            for page in reader.pages[:max_pages]:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_chunks.append(page_text)
                if sum(len(chunk) for chunk in text_chunks) >= MAX_REPORT_TEXT_CHARS:
                    break
            extraction_method = "pypdf_text" if text_chunks else extraction_method
        except Exception:
            pass

    text_excerpt = re.sub(r"\s+", " ", "\n".join(text_chunks)).strip()[:MAX_REPORT_TEXT_CHARS]
    table_text = re.sub(r"\s+", " ", "\n".join(table_text_chunks)).strip()[:MAX_TABLE_TEXT_CHARS]
    return {
        "text_excerpt": text_excerpt,
        "table_text": table_text,
        "tables": structured_tables[:25],
        "table_count": len(structured_tables),
        "pages_scanned": max((table.get("page", 0) for table in structured_tables), default=0),
        "extraction_method": extraction_method,
    }


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
        "/investor-relations",
        "/investors",
        "/investor",
        "/financials",
        "/reports",
        "/annual-report",
        "/annual-reports",
        "/integrated-report",
        "/en/investor-relations",
        "/en/investors",
        "/en/annual-report",
        "/id/tentang-bca/hubungan-investor/laporan-tahunan",
        "/en/about-bca/investor-relations/annual-report",
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
            if any(token in text for token in ["annual", "report", "laporan", "10-k", "20-f", ".pdf"]):
                found.append(link)
    return found


async def discover_annual_report(company_name: str, symbol: str, website: Optional[str] = None) -> Optional[Dict[str, Any]]:
    company_name = (company_name or "").strip()
    symbol = _clean_symbol(symbol)
    website = website or ""
    official_host = _host(website)
    base_symbol = symbol.split(".", 1)[0]

    search_queries = [
        f'"{company_name}" "annual report" pdf',
        f'"{company_name}" "integrated report" pdf',
        f'"{company_name}" "form 10-k" pdf',
        f'"{company_name}" "20-f" pdf',
        f'"{company_name}" "laporan tahunan" pdf',
        f'"{symbol}" "annual report" pdf',
        f'"{base_symbol}" "annual report" pdf',
        f'site:annualreports.com "{company_name}"',
        f'site:sec.gov "{company_name}" "10-K"',
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
            score = _annual_report_score(url, title, official_host)
            if score <= 30:
                continue
            deduped[url] = {"url": url, "title": title}

        ranked = sorted(
            deduped.values(),
            key=lambda item: _annual_report_score(item["url"], item.get("title", ""), official_host),
            reverse=True,
        )

        pdf_candidates: List[Dict[str, str]] = []
        for item in ranked[:20]:
            url = item["url"]
            if _is_pdf_url(url):
                pdf_candidates.append(item)
                continue
            try:
                page_html = await _download_text(client, url)
                for link in _extract_links(page_html, url):
                    score = _annual_report_score(link.get("url", ""), link.get("title", ""), official_host)
                    if _is_pdf_url(link.get("url", "")) and score > 25:
                        pdf_candidates.append(link)
            except Exception:
                continue

        pdf_deduped: Dict[str, Dict[str, str]] = {item["url"]: item for item in pdf_candidates if item.get("url")}
        pdf_ranked = sorted(
            pdf_deduped.values(),
            key=lambda item: _annual_report_score(item["url"], item.get("title", ""), official_host),
            reverse=True,
        )

        for item in pdf_ranked[:10]:
            pdf_url = item["url"]
            try:
                pdf_bytes = await _download_bytes(client, pdf_url)
                pdf_content = _extract_pdf_content(pdf_bytes)
                combined_for_year = f"{item.get('title', '')} {pdf_url} {pdf_content.get('text_excerpt', '')[:1000]} {pdf_content.get('table_text', '')[:1000]}"
                years = re.findall(r"20\d{2}", combined_for_year)
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
                    **pdf_content,
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


def _normalize_decimal_number(text: str) -> Optional[float]:
    raw = (text or "").strip().replace(" ", "")
    raw = raw.replace("%", "").replace("(", "-").replace(")", "")
    if not raw:
        return None
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        tail = raw.rsplit(",", 1)[-1]
        raw = raw.replace(",", ".") if len(tail) <= 2 else raw.replace(",", "")
    elif "." in raw:
        tail = raw.rsplit(".", 1)[-1]
        if len(tail) == 3 and len(raw.split(".")[0]) <= 3:
            raw = raw.replace(".", "")
    try:
        return float(raw)
    except Exception:
        return None


def _ratio_from_percent(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return value / 100 if abs(value) > 1.5 else value


def _alias_regex(alias: str) -> str:
    return re.escape(alias).replace(r"\ ", r"\s+")


def _extract_percentage_metric(text: str, aliases: List[str]) -> Optional[float]:
    if not text:
        return None
    for alias in aliases:
        pattern_after = re.compile(rf"(?:{_alias_regex(alias)})[^0-9%\-]{{0,120}}(-?\(?\d+(?:[\.,]\d+)?\)?)[ ]*%", re.I)
        match = pattern_after.search(text)
        if match:
            return _ratio_from_percent(_normalize_decimal_number(match.group(1)))
        pattern_before = re.compile(rf"(-?\(?\d+(?:[\.,]\d+)?\)?)[ ]*%[^A-Za-z0-9]{{0,70}}(?:{_alias_regex(alias)})", re.I)
        match = pattern_before.search(text)
        if match:
            return _ratio_from_percent(_normalize_decimal_number(match.group(1)))
    return None


def _amount_multiplier(unit: str) -> float:
    unit = (unit or "").lower()
    if unit in {"trillion", "triliun"}:
        return 1_000_000_000_000
    if unit in {"billion", "miliar", "bn"}:
        return 1_000_000_000
    if unit in {"million", "juta", "mn"}:
        return 1_000_000
    return 1


def _extract_amount_metric(text: str, aliases: List[str]) -> Optional[float]:
    if not text:
        return None
    units = r"(trillion|triliun|billion|miliar|million|juta|bn|mn)?"
    for alias in aliases:
        pattern = re.compile(rf"(?:{_alias_regex(alias)})[^0-9\-\(]{{0,140}}(-?\(?\d[\d\.,]*\)?)\s*{units}", re.I)
        match = pattern.search(text)
        if match:
            number = _normalize_decimal_number(match.group(1))
            if number is None:
                continue
            return number * _amount_multiplier(match.group(2) or "")
    return None


def _row_contains_alias(row_text: str, aliases: List[str]) -> bool:
    row_text = row_text.lower()
    return any(re.search(rf"\b{_alias_regex(alias.lower())}\b", row_text) for alias in aliases)


def _numeric_candidates_from_cells(cells: List[str], as_ratio: bool) -> List[Tuple[int, float]]:
    candidates: List[Tuple[int, float]] = []
    for index, cell in enumerate(cells):
        clean = _clean_cell(cell)
        if not clean:
            continue
        matches = re.findall(r"-?\(?\d[\d\.,]*\)?\s*%?", clean)
        for match in matches:
            value = _normalize_decimal_number(match)
            if value is None:
                continue
            if as_ratio:
                if "%" in clean or abs(value) > 1.5:
                    value = _ratio_from_percent(value) or value
                if abs(value) > 10:
                    continue
            candidates.append((index, value))
    return candidates


def _year_column_indexes(table_rows: List[List[str]]) -> Dict[int, int]:
    best: Dict[int, int] = {}
    for row in table_rows[:6]:
        for index, cell in enumerate(row):
            years = re.findall(r"20\d{2}", cell or "")
            for year in years:
                best[int(year)] = index
    return best


def _extract_metric_from_tables(tables: List[Dict[str, Any]], aliases: List[str], as_ratio: bool) -> Optional[float]:
    for table in tables or []:
        rows = table.get("rows") or []
        split_rows = [[_clean_cell(cell) for cell in str(row).split("|")] for row in rows]
        year_columns = _year_column_indexes(split_rows)
        preferred_indexes = [year_columns[max(year_columns)]] if year_columns else []
        for cells in split_rows:
            row_text = " ".join(cells)
            if not _row_contains_alias(row_text, aliases):
                continue
            numeric_cells = _numeric_candidates_from_cells(cells, as_ratio=as_ratio)
            if not numeric_cells:
                continue
            for preferred_index in preferred_indexes:
                for cell_index, value in numeric_cells:
                    if cell_index == preferred_index:
                        return value
            label_side_numbers = [(index, value) for index, value in numeric_cells if index > 0]
            if label_side_numbers:
                return label_side_numbers[0][1]
            return numeric_cells[0][1]
    return None


def extract_bank_kpis_from_annual_report(annual_report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not annual_report or annual_report.get("status") != "found":
        return {}
    text = annual_report.get("text_excerpt") or ""
    table_text = annual_report.get("table_text") or ""
    tables = annual_report.get("tables") or []
    combined_text = f"{table_text}\n{text}"
    if not combined_text.strip() and not tables:
        return {}

    extracted: Dict[str, Any] = {}
    evidence: Dict[str, str] = {}
    for metric, aliases in BANK_KPI_ALIASES.items():
        as_ratio = metric in RATIO_KPIS
        table_value = _extract_metric_from_tables(tables, aliases, as_ratio=as_ratio)
        text_value = _extract_percentage_metric(combined_text, aliases) if as_ratio else _extract_amount_metric(combined_text, aliases)
        value = table_value if table_value is not None else text_value
        if value is not None:
            extracted[metric] = value
            evidence[metric] = "table" if table_value is not None else "text"

    if extracted:
        extracted["_extraction_evidence"] = evidence
        extracted["_table_count"] = annual_report.get("table_count", 0)
        extracted["_extraction_method"] = annual_report.get("extraction_method")
    return extracted


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
    if profile:
        annual_report = await discover_annual_report(
            profile.get("companyName") or profile.get("name") or requested_symbol,
            requested_symbol,
            profile.get("website"),
        )
        endpoint_payloads["annual_report"] = annual_report
        if annual_report and annual_report.get("status") == "found":
            endpoint_payloads["annual_report_bank_kpis"] = extract_bank_kpis_from_annual_report(annual_report)
            resolved_any = True
        elif annual_report:
            warnings.append("annual_report: not_found")

    return {
        "provider": "fmp",
        "requested_symbol": requested_symbol,
        "resolved_symbol": resolved_symbol,
        "retrieved_at": utc_now(),
        "status": "success" if resolved_any else "provider_gap",
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

    provider_payload = {"profile": profile}
    if endpoints.get("annual_report"):
        provider_payload["annual_report"] = endpoints.get("annual_report")
    if endpoints.get("annual_report_bank_kpis"):
        provider_payload["annual_report_bank_kpis"] = endpoints.get("annual_report_bank_kpis")

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
    text = " ".join(str(profile.get(field) or "") for field in ["sector", "industry", "company_name", "description"]).lower()
    return any(token in text for token in ["bank", "banc", "financial services", "lender", "credit institution"])


def _first_non_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def calculate_bank_kpi_row(symbol: str, bundle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    endpoints = bundle.get("endpoints") or {}
    profile = normalize_profile(symbol, bundle) or {}
    annual_report = endpoints.get("annual_report") or {}
    annual_report_kpis = endpoints.get("annual_report_bank_kpis") or extract_bank_kpis_from_annual_report(annual_report)
    if not _looks_like_bank(profile) and not annual_report_kpis:
        return None

    ratios = _first_list_row(endpoints.get("ratios"))
    metrics = _first_list_row(endpoints.get("key_metrics"))
    if not ratios and not metrics and not annual_report_kpis:
        return None

    report_year = annual_report.get("report_year") if isinstance(annual_report, dict) else None
    fiscal_year = _safe_fiscal_year(ratios.get("calendarYear") or metrics.get("calendarYear") or report_year, _iso_date(ratios.get("date") or metrics.get("date")))
    fiscal_period = str(ratios.get("period") or metrics.get("period") or "FY").upper()
    period_type = "quarterly" if fiscal_period in {"Q1", "Q2", "Q3", "Q4"} else "annual"
    evidence = annual_report_kpis.get("_extraction_evidence", {}) if isinstance(annual_report_kpis, dict) else {}
    extraction_method = annual_report_kpis.get("_extraction_method") if isinstance(annual_report_kpis, dict) else None

    row = {
        "symbol": _clean_symbol(symbol),
        "provider_symbol": _clean_symbol(str(profile.get("provider_symbol") or symbol)),
        "fiscal_year": fiscal_year,
        "fiscal_period": fiscal_period,
        "period_type": period_type,
        "total_loans": annual_report_kpis.get("total_loans"),
        "total_deposits": annual_report_kpis.get("customer_deposits"),
        "customer_deposits": annual_report_kpis.get("customer_deposits"),
        "net_interest_income": annual_report_kpis.get("net_interest_income"),
        "net_income": annual_report_kpis.get("net_income"),
        "total_assets": annual_report_kpis.get("total_assets"),
        "total_equity": annual_report_kpis.get("total_equity"),
        "nim": annual_report_kpis.get("nim"),
        "roe": _first_non_none(annual_report_kpis.get("roe"), _number(ratios.get("returnOnEquity"))),
        "roa": _first_non_none(annual_report_kpis.get("roa"), _number(ratios.get("returnOnAssets"))),
        "npl_ratio": annual_report_kpis.get("npl_ratio"),
        "loan_to_deposit_ratio": annual_report_kpis.get("loan_to_deposit_ratio"),
        "casa_ratio": annual_report_kpis.get("casa_ratio"),
        "car": annual_report_kpis.get("car"),
        "cost_to_income_ratio": annual_report_kpis.get("cost_to_income_ratio"),
        "return_on_assets": _first_non_none(annual_report_kpis.get("roa"), _number(ratios.get("returnOnAssets"))),
        "return_on_equity": _first_non_none(annual_report_kpis.get("roe"), _number(ratios.get("returnOnEquity"))),
        "debt_to_equity": _number(ratios.get("debtEquityRatio")),
        "price_to_book": _number(ratios.get("priceToBookRatio")),
        "tier1_proxy": _number(metrics.get("tangibleAssetValue")) or _number(metrics.get("netCurrentAssetValue")),
        "loan_to_deposit": annual_report_kpis.get("loan_to_deposit_ratio"),
        "efficiency_ratio": annual_report_kpis.get("cost_to_income_ratio"),
        "source": "annual_report_table+fmp" if evidence and any(value == "table" for value in evidence.values()) else ("annual_report+fmp" if annual_report_kpis else "fmp"),
        "source_confidence": 0.88 if evidence and any(value == "table" for value in evidence.values()) else (0.82 if annual_report_kpis else SOURCE_CONFIDENCE),
        "provider_payload": {
            "annual_report": annual_report,
            "annual_report_bank_kpis": annual_report_kpis,
            "extraction_evidence": evidence,
            "extraction_method": extraction_method,
            "fmp_ratios_available": bool(ratios),
            "fmp_metrics_available": bool(metrics),
        },
        "note": "Bank KPIs are extracted from annual-report tables/text when API coverage is incomplete; table-derived values are preferred but should still be reviewed for critical decisions." if annual_report_kpis else "FMP coverage for bank-specific KPIs is partial; blank fields indicate provider gaps.",
        "retrieved_at": bundle.get("retrieved_at") or utc_now(),
        "updated_at": utc_now(),
    }
    return row


def build_metric_coverage(
    symbol: str,
    years: List[int],
    statement_rows: List[Dict[str, Any]],
    valuation: Optional[Dict[str, Any]],
    bank_kpi: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    requirements = {
        "income_statement": {"revenue": {"revenue", "totalRevenue"}, "net_income": {"netIncome", "netIncomeRatio"}},
        "balance_sheet": {"total_assets": {"totalAssets"}, "total_equity": {"totalStockholdersEquity", "totalEquity"}},
        "cash_flow": {"operating_cash_flow": {"operatingCashFlow"}, "free_cash_flow": {"freeCashFlow"}},
    }

    lookup = {(row.get("fiscal_year"), row.get("statement_type"), row.get("metric_name")): row for row in statement_rows}
    coverage_rows: List[Dict[str, Any]] = []
    now = utc_now()
    any_statement_data = bool(statement_rows)
    latest_year = years[0] if years else datetime.now(timezone.utc).year

    for year in years:
        for metric_group, metric_map in requirements.items():
            for metric_name, aliases in metric_map.items():
                matched = any(lookup.get((year, metric_group, alias)) is not None for alias in aliases)
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
            "roe",
            "roa",
            "nim",
            "npl_ratio",
            "loan_to_deposit_ratio",
            "casa_ratio",
            "car",
            "cost_to_income_ratio",
            "debt_to_equity",
            "price_to_book",
            "tier1_proxy",
            "total_assets",
            "total_equity",
            "total_loans",
            "customer_deposits",
            "net_interest_income",
            "net_income",
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
                    "note": "" if metric_value is not None else "Provider/report parser did not return this bank KPI.",
                    "source": bank_kpi.get("source") or "fmp",
                    "source_confidence": bank_kpi.get("source_confidence") or SOURCE_CONFIDENCE,
                    "updated_at": now,
                }
            )

    return coverage_rows
