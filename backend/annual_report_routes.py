import asyncio
import html
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

import httpx
from pydantic import BaseModel

from main import (
    ask_qwen,
    clean_text,
    load_warehouse_snapshot,
    norm_symbol,
    qwen_is_configured,
    resolve_single_ticker,
    supabase_is_configured,
    supabase_upsert,
    utc_now,
)

SUPABASE_ANNUAL_REPORT_TABLE = "qfin_annual_report_sources"
REPORT_KEYWORDS = ["annual", "report", "laporan", "tahunan", "ar-"]
USER_AGENT = "Mozilla/5.0 (compatible; QFinTerminal/1.0; +https://qfin-terminal.onrender.com)"


class AnnualReportSearchRequest(BaseModel):
    report_year: Optional[int] = None
    company_name: Optional[str] = None
    candidate_urls: Optional[List[str]] = None
    save: bool = True
    max_candidates: Optional[int] = 12


def extract_json_object(text: str) -> Dict[str, Any]:
    cleaned = clean_text(text or "")
    cleaned = re.sub(r"^```(?:json)?", "", cleaned.strip(), flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def domain_from_url(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().split("@")[-1].split(":")[0]
    except Exception:
        return ""


def clean_candidate_url(url: str) -> Optional[str]:
    value = html.unescape(clean_text(url or ""))
    if not value or len(value) > 1200:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return None
    domain = domain_from_url(value)
    if not domain or domain in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return None
    if domain.endswith(".local") or domain.startswith("10.") or domain.startswith("192.168."):
        return None
    return value


def normalize_company_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").lower()).strip()


def official_annual_report_domains(symbol: str, company_name: Optional[str] = None) -> List[str]:
    normalized = norm_symbol(symbol)
    company = normalize_company_text(company_name or "")
    domains: List[str] = []

    if normalized == "BBCA.JK" or "bank central asia" in company or company == "bca":
        domains.extend(["bca.co.id", "www.bca.co.id"])
    if normalized.endswith(".JK"):
        domains.extend(["idx.co.id", "www.idx.co.id"])
    if normalized.endswith(".SI"):
        domains.extend(["sgx.com", "links.sgx.com"])
    if normalized.endswith(".KL"):
        domains.extend(["bursamalaysia.com", "www.bursamalaysia.com"])

    seen: set[str] = set()
    result: List[str] = []
    for domain in domains:
        clean_domain = domain.lower().strip()
        if clean_domain and clean_domain not in seen:
            result.append(clean_domain)
            seen.add(clean_domain)
    return result


def annual_report_landing_pages(symbol: str, company_name: str) -> List[str]:
    normalized = norm_symbol(symbol)
    company = normalize_company_text(company_name)
    pages: List[str] = []

    if normalized == "BBCA.JK" or "bank central asia" in company or company == "bca":
        pages.extend(
            [
                "https://www.bca.co.id/en/tentang-bca/Hubungan-Investor/laporan-presentasi/Laporan-Tahunan",
                "https://www.bca.co.id/id/tentang-bca/Hubungan-Investor/laporan-presentasi/Laporan-Tahunan",
            ]
        )

    return list(dict.fromkeys(pages))


def annual_report_search_prompt(
    symbol: str,
    company_name: str,
    report_year: int,
    allowed_domains: List[str],
    user_candidate_urls: List[str],
    discovered_candidates: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    domain_text = ", ".join(allowed_domains) if allowed_domains else "official company investor relations website and official exchange website"
    candidates_text = "\n".join(f"- {url}" for url in user_candidate_urls[:10]) or "None supplied."
    discovered_text = "\n".join(
        f"- {item.get('title')}: {item.get('url')}"
        for item in discovered_candidates[:12]
    ) or "None discovered yet."
    return [
        {
            "role": "system",
            "content": (
                "You are QFin's annual report source finder and ranking layer. Return JSON only. "
                "Rank official annual report sources, not financial table data. "
                "Prefer direct annual-report PDFs first, then official company investor relations annual-report pages, "
                "then official exchange filing pages. Avoid random blogs, PDF mirrors, Scribd, SEO pages, and unsafe links."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Ticker: {symbol}\n"
                f"Company: {company_name}\n"
                f"Target report year: {report_year}\n"
                f"Allowed/preferred domains: {domain_text}\n"
                f"User supplied candidate URLs:\n{candidates_text}\n\n"
                f"Backend-discovered official candidates:\n{discovered_text}\n\n"
                "Return this exact JSON shape only:\n"
                "{\n"
                "  \"status\": \"found | needs_search | not_found\",\n"
                "  \"recommended_query\": \"best search query\",\n"
                "  \"search_queries\": [\"query 1\", \"query 2\"],\n"
                "  \"candidates\": [\n"
                "    {\"title\": \"...\", \"url\": \"https://...\", \"source_domain\": \"...\", \"year\": 2025, \"confidence\": 0.0, \"reason\": \"...\"}\n"
                "  ]\n"
                "}\n"
                "Only include URLs that are plausible official annual report or investor relations pages."
            ),
        },
    ]


def detect_year(text: str, default_year: int) -> int:
    years = [int(item) for item in re.findall(r"\b20\d{2}\b", text or "")]
    if default_year in years:
        return default_year
    if years:
        return max(years)
    return default_year


def candidate_from_url(
    url: str,
    *,
    title: str,
    year: int,
    confidence: float,
    reason: str,
    provider: str,
    source_kind: str,
    discovered_from: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    clean_url = clean_candidate_url(url)
    if not clean_url:
        return None
    return {
        "title": clean_text(title)[:220] or f"Annual Report {year}",
        "url": clean_url,
        "source_domain": domain_from_url(clean_url),
        "year": year,
        "confidence": max(0.0, min(1.0, float(confidence or 0.0))),
        "reason": clean_text(reason)[:700],
        "provider": provider,
        "source_kind": source_kind,
        "discovered_from": discovered_from,
    }


def normalize_report_candidate(candidate: Dict[str, Any], default_year: int, provider: str = "qwen_search") -> Optional[Dict[str, Any]]:
    if not isinstance(candidate, dict):
        return None
    url = clean_candidate_url(str(candidate.get("url") or ""))
    if not url:
        return None
    domain = domain_from_url(url)
    try:
        confidence = float(candidate.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    try:
        year = int(candidate.get("year") or detect_year(url, default_year))
    except Exception:
        year = default_year
    return {
        "title": clean_text(str(candidate.get("title") or f"Annual Report {year}"))[:220],
        "url": url,
        "source_domain": clean_text(str(candidate.get("source_domain") or domain))[:180],
        "year": year,
        "confidence": max(0.0, min(1.0, confidence)),
        "reason": clean_text(str(candidate.get("reason") or "Annual report candidate."))[:700],
        "provider": clean_text(str(candidate.get("provider") or provider))[:80],
        "source_kind": clean_text(str(candidate.get("source_kind") or "candidate"))[:80],
        "discovered_from": candidate.get("discovered_from"),
    }


def extract_links_from_html(page_url: str, text: str, report_year: int) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not text:
        return results

    for match in re.finditer(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", text, flags=re.I | re.S):
        href = html.unescape(match.group(1) or "")
        label = clean_text(re.sub(r"<[^>]+>", " ", html.unescape(match.group(2) or "")))
        url = clean_candidate_url(urljoin(page_url, href))
        if not url:
            continue
        lower_blob = f"{url} {label}".lower()
        if not any(token in lower_blob for token in REPORT_KEYWORDS) and ".pdf" not in lower_blob:
            continue
        context_start = max(0, match.start() - 500)
        context_end = min(len(text), match.end() + 500)
        context = clean_text(re.sub(r"<[^>]+>", " ", html.unescape(text[context_start:context_end])))
        year = detect_year(f"{url} {label} {context}", report_year)
        confidence = 0.82
        if year == report_year:
            confidence += 0.08
        if url.lower().endswith(".pdf"):
            confidence += 0.06
        title = label or f"Annual Report {year}"
        candidate = candidate_from_url(
            url,
            title=title,
            year=year,
            confidence=confidence,
            reason=f"Found on official annual report landing page: {page_url}",
            provider="official_page_discovery",
            source_kind="pdf" if url.lower().endswith(".pdf") else "official_link",
            discovered_from=page_url,
        )
        if candidate:
            results.append(candidate)

    return results


async def fetch_text(url: str, timeout_seconds: float = 10.0) -> Dict[str, Any]:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout_seconds, headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(url, headers={"Range": "bytes=0-120000"})
            return {
                "ok": response.status_code < 400,
                "status_code": response.status_code,
                "mime_type": response.headers.get("content-type"),
                "text": response.text[:120000],
                "url": str(response.url),
            }
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "text": "", "url": url}


async def discover_from_official_pages(symbol: str, company_name: str, report_year: int) -> List[Dict[str, Any]]:
    pages = annual_report_landing_pages(symbol, company_name)
    if not pages:
        return []

    discovered: List[Dict[str, Any]] = []
    responses = await asyncio.gather(*(fetch_text(page) for page in pages))
    for page, response in zip(pages, responses):
        text = response.get("text") or ""
        if response.get("ok"):
            page_candidate = candidate_from_url(
                page,
                title=f"Official Annual Report page {report_year}",
                year=report_year,
                confidence=0.9 if str(report_year) in text else 0.78,
                reason="Known official investor relations annual report landing page.",
                provider="official_page_discovery",
                source_kind="annual_report_index",
                discovered_from=None,
            )
            if page_candidate:
                discovered.append(page_candidate)
            discovered.extend(extract_links_from_html(page, text, report_year))

    return discovered


def decode_duckduckgo_url(url: str) -> str:
    parsed = urlparse(html.unescape(url))
    qs = parse_qs(parsed.query)
    if "uddg" in qs and qs["uddg"]:
        return qs["uddg"][0]
    return url


def query_allowed_domains(query: str, allowed_domains: List[str]) -> str:
    if not allowed_domains:
        return query
    domain_filter = " OR ".join(f"site:{domain}" for domain in allowed_domains[:4])
    return f"({domain_filter}) {query}"


async def search_web_candidates(query: str, report_year: int, allowed_domains: List[str], limit: int = 8) -> List[Dict[str, Any]]:
    search_url = f"https://duckduckgo.com/html/?q={quote_plus(query_allowed_domains(query, allowed_domains))}"
    response = await fetch_text(search_url, timeout_seconds=12.0)
    text = response.get("text") or ""
    candidates: List[Dict[str, Any]] = []
    if not response.get("ok") or not text:
        return candidates

    matches = list(re.finditer(r"<a[^>]+class=[\"'][^\"']*result__a[^\"']*[\"'][^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", text, flags=re.I | re.S))
    if not matches:
        matches = list(re.finditer(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", text, flags=re.I | re.S))

    for match in matches:
        raw_url = decode_duckduckgo_url(match.group(1) or "")
        url = clean_candidate_url(raw_url)
        if not url:
            continue
        domain = domain_from_url(url)
        if allowed_domains and not any(domain == item or domain.endswith(f".{item}") for item in allowed_domains):
            continue
        label = clean_text(re.sub(r"<[^>]+>", " ", html.unescape(match.group(2) or "")))
        blob = f"{url} {label}".lower()
        if not any(token in blob for token in REPORT_KEYWORDS) and str(report_year) not in blob:
            continue
        year = detect_year(blob, report_year)
        confidence = 0.66
        if year == report_year:
            confidence += 0.08
        if url.lower().endswith(".pdf"):
            confidence += 0.06
        candidate = candidate_from_url(
            url,
            title=label or f"Search result annual report {year}",
            year=year,
            confidence=confidence,
            reason=f"Found from web search query: {query}",
            provider="web_search",
            source_kind="search_result_pdf" if url.lower().endswith(".pdf") else "search_result",
            discovered_from=search_url,
        )
        if candidate:
            candidates.append(candidate)
        if len(candidates) >= limit:
            break
    return candidates


async def validate_annual_report_candidate(candidate: Dict[str, Any], allowed_domains: List[str]) -> Dict[str, Any]:
    url = candidate.get("url") or ""
    domain = domain_from_url(url)
    allowed = not allowed_domains or any(domain == item or domain.endswith(f".{item}") for item in allowed_domains)
    validation_notes: List[str] = []
    if not allowed:
        validation_notes.append("Domain is outside the preferred official domain list.")

    http_status: Optional[int] = None
    mime_type: Optional[str] = None
    is_reachable = False
    body_sample = ""
    final_url = url
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0, headers={"User-Agent": USER_AGENT}) as client:
            response = await client.head(url)
            http_status = response.status_code
            mime_type = response.headers.get("content-type")
            if response.status_code in {403, 405} or response.status_code >= 500 or not mime_type:
                response = await client.get(url, headers={"Range": "bytes=0-120000"})
                http_status = response.status_code
                mime_type = response.headers.get("content-type")
                if "text" in (mime_type or "").lower() or "html" in (mime_type or "").lower():
                    body_sample = response.text[:120000]
            elif "text" in (mime_type or "").lower() or "html" in (mime_type or "").lower():
                response = await client.get(url, headers={"Range": "bytes=0-120000"})
                http_status = response.status_code
                mime_type = response.headers.get("content-type")
                body_sample = response.text[:120000]
            final_url = str(response.url)
            is_reachable = response.status_code < 400
    except Exception as exc:
        validation_notes.append(f"Validation request failed: {type(exc).__name__}")

    lower_url = final_url.lower()
    lower_body = clean_text(re.sub(r"<[^>]+>", " ", html.unescape(body_sample))).lower()[:6000]
    year_text = str(candidate.get("year") or "")
    looks_like_report = (
        any(token in lower_url for token in REPORT_KEYWORDS)
        or lower_url.endswith(".pdf")
        or any(token in lower_body for token in ["annual report", "laporan tahunan", "download annual report"])
    )
    year_match = bool(year_text and (year_text in lower_url or year_text in lower_body or candidate.get("source_kind") == "annual_report_index"))
    is_pdf = lower_url.endswith(".pdf") or (mime_type and "pdf" in mime_type.lower())

    if not looks_like_report:
        validation_notes.append("URL/content does not clearly look like an annual report page or PDF.")
    if not year_match:
        validation_notes.append("Target report year was not clearly confirmed from URL/content.")

    is_valid = bool(allowed and is_reachable and looks_like_report and (year_match or is_pdf))
    confidence = float(candidate.get("confidence") or 0.0)
    if allowed:
        confidence = min(1.0, confidence + 0.08)
    if is_reachable:
        confidence = min(1.0, confidence + 0.08)
    if year_match:
        confidence = min(1.0, confidence + 0.08)
    if is_pdf:
        confidence = min(1.0, confidence + 0.08)

    return {
        **candidate,
        "url": final_url,
        "source_domain": domain_from_url(final_url) or candidate.get("source_domain"),
        "confidence": round(confidence, 4),
        "http_status": http_status,
        "mime_type": mime_type,
        "is_reachable": is_reachable,
        "is_pdf": bool(is_pdf),
        "year_confirmed": bool(year_match),
        "is_valid": is_valid,
        "validation_notes": validation_notes,
    }


def annual_report_supabase_row(symbol: str, company_name: str, candidate: Dict[str, Any], rank: int) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "company_name": company_name,
        "report_year": candidate.get("year"),
        "title": candidate.get("title"),
        "url": candidate.get("url"),
        "source_domain": candidate.get("source_domain"),
        "source_type": "annual_report",
        "source_kind": candidate.get("source_kind"),
        "discovered_from": candidate.get("discovered_from"),
        "confidence": candidate.get("confidence"),
        "status": "validated" if candidate.get("is_valid") else "candidate",
        "reason": candidate.get("reason"),
        "provider": candidate.get("provider") or "qwen_search",
        "candidate_rank": rank,
        "http_status": candidate.get("http_status"),
        "mime_type": candidate.get("mime_type"),
        "is_valid": bool(candidate.get("is_valid")),
        "validation_notes": candidate.get("validation_notes") or [],
        "raw_payload": candidate,
        "updated_at": utc_now(),
    }


def dedupe_candidates(candidates: List[Dict[str, Any]], max_candidates: int) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    for candidate in sorted(candidates, key=lambda item: float(item.get("confidence") or 0), reverse=True):
        url = candidate.get("url")
        if not url or url in seen_urls:
            continue
        deduped.append(candidate)
        seen_urls.add(url)
        if len(deduped) >= max_candidates:
            break
    return deduped


async def search_annual_report_source(symbol: str, payload: AnnualReportSearchRequest) -> Dict[str, Any]:
    resolved = resolve_single_ticker(symbol, allow_search=False) or resolve_single_ticker(symbol) or norm_symbol(symbol)
    snapshot = load_warehouse_snapshot(resolved)
    profile = snapshot.get("profile") if isinstance(snapshot, dict) else None
    company_name = clean_text(
        payload.company_name
        or (profile or {}).get("company_name")
        or (profile or {}).get("name")
        or resolved
    )
    report_year = payload.report_year or datetime.now(timezone.utc).year - 1
    max_candidates = max(3, min(int(payload.max_candidates or 12), 20))
    user_urls = [url for url in (payload.candidate_urls or []) if clean_candidate_url(url)]
    allowed_domains = official_annual_report_domains(resolved, company_name)

    deterministic_candidates: List[Dict[str, Any]] = []
    for url in user_urls:
        candidate = candidate_from_url(
            url,
            title=f"User supplied annual report candidate {report_year}",
            year=report_year,
            confidence=0.62,
            reason="User supplied candidate URL.",
            provider="user_candidate",
            source_kind="user_supplied",
        )
        if candidate:
            deterministic_candidates.append(candidate)

    deterministic_candidates.extend(await discover_from_official_pages(resolved, company_name, report_year))

    qwen_payload: Dict[str, Any] = {
        "status": "needs_search",
        "recommended_query": f"{company_name} annual report {report_year} pdf official",
        "search_queries": [
            f"{company_name} annual report {report_year} pdf official",
            f"{resolved} annual report {report_year} investor relations",
            f"{company_name} laporan tahunan {report_year} pdf",
        ],
        "candidates": [],
    }

    qwen_error: Optional[str] = None
    if qwen_is_configured():
        try:
            qwen_text = await ask_qwen(
                annual_report_search_prompt(
                    resolved,
                    company_name,
                    report_year,
                    allowed_domains,
                    user_urls,
                    deterministic_candidates,
                )
            )
            parsed = extract_json_object(qwen_text)
            if parsed:
                qwen_payload.update(parsed)
        except Exception as exc:
            qwen_error = f"Qwen search planning failed: {type(exc).__name__}"
    else:
        qwen_error = "Qwen is not configured. Returning deterministic source discovery and search queries only."

    search_queries = [str(item) for item in (qwen_payload.get("search_queries") or []) if clean_text(str(item))]
    if not search_queries:
        search_queries = qwen_payload["search_queries"]

    web_candidates: List[Dict[str, Any]] = []
    if len(deterministic_candidates) < max_candidates:
        search_batches = await asyncio.gather(
            *(search_web_candidates(query, report_year, allowed_domains, limit=5) for query in search_queries[:3])
        )
        for batch in search_batches:
            web_candidates.extend(batch)

    qwen_candidates: List[Dict[str, Any]] = []
    for item in qwen_payload.get("candidates") or []:
        normalized = normalize_report_candidate(item, report_year, provider="qwen_search")
        if normalized:
            qwen_candidates.append(normalized)

    raw_candidates = dedupe_candidates(
        deterministic_candidates + qwen_candidates + web_candidates,
        max_candidates=max_candidates,
    )

    if raw_candidates:
        validated = await asyncio.gather(
            *(validate_annual_report_candidate(candidate, allowed_domains) for candidate in raw_candidates)
        )
    else:
        validated = []
    validated = sorted(
        validated,
        key=lambda item: (
            bool(item.get("is_valid")),
            bool(item.get("is_pdf")),
            bool(item.get("year_confirmed")),
            float(item.get("confidence") or 0),
        ),
        reverse=True,
    )
    recommended = validated[0] if validated else None

    storage = "not_saved"
    if payload.save and supabase_is_configured() and validated:
        rows = [annual_report_supabase_row(resolved, company_name, candidate, index + 1) for index, candidate in enumerate(validated)]
        try:
            supabase_upsert(
                SUPABASE_ANNUAL_REPORT_TABLE,
                rows,
                on_conflict="symbol,url",
            )
            storage = "supabase"
        except Exception as exc:
            storage = f"save_failed: {str(exc)[:220]}"

    valid_count = sum(1 for item in validated if item.get("is_valid"))
    status = "found" if valid_count else "needs_search"
    if not validated and qwen_payload.get("status") == "not_found":
        status = "not_found"

    return {
        "status": status,
        "symbol": resolved,
        "company_name": company_name,
        "report_year": report_year,
        "allowed_domains": allowed_domains,
        "recommended_source": recommended,
        "valid_source_count": valid_count,
        "candidates": validated,
        "search_queries": search_queries,
        "recommended_query": qwen_payload.get("recommended_query"),
        "qwen_status": qwen_payload.get("status"),
        "qwen_error": qwen_error,
        "storage": storage,
        "note": "This endpoint searches official investor-relations pages, ranks candidates with Qwen when available, validates URLs, and saves source metadata. It does not crawl whole sites or extract financial tables.",
    }


def register_annual_report_routes(app) -> None:
    @app.post("/annual-report/search/{symbol}")
    async def annual_report_search_route(symbol: str, payload: Optional[AnnualReportSearchRequest] = None) -> Dict[str, Any]:
        return await search_annual_report_source(symbol, payload or AnnualReportSearchRequest())
