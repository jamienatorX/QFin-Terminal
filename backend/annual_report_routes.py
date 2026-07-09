import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

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


class AnnualReportSearchRequest(BaseModel):
    report_year: Optional[int] = None
    company_name: Optional[str] = None
    candidate_urls: Optional[List[str]] = None
    save: bool = True


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
        return (urlparse(url).netloc or "").lower().split("@")[ -1].split(":")[0]
    except Exception:
        return ""


def clean_candidate_url(url: str) -> Optional[str]:
    value = clean_text(url or "")
    if not value or len(value) > 800:
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


def annual_report_search_prompt(
    symbol: str,
    company_name: str,
    report_year: int,
    allowed_domains: List[str],
    user_candidate_urls: List[str],
) -> List[Dict[str, str]]:
    domain_text = ", ".join(allowed_domains) if allowed_domains else "official company investor relations website and official exchange website"
    candidates_text = "\n".join(f"- {url}" for url in user_candidate_urls[:10]) or "None supplied."
    return [
        {
            "role": "system",
            "content": (
                "You are QFin's annual report source finder. Return JSON only. "
                "Identify official annual report source candidates, not financial table data. "
                "Prefer company investor relations pages, then official exchange filings. "
                "Avoid random blogs, PDF mirrors, Scribd, SEO pages, and unsafe links."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Find likely official annual report source candidates for ticker {symbol}.\n"
                f"Company: {company_name}\n"
                f"Target report year: {report_year}\n"
                f"Allowed/preferred domains: {domain_text}\n"
                f"User supplied candidate URLs:\n{candidates_text}\n\n"
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


def normalize_report_candidate(candidate: Dict[str, Any], default_year: int) -> Optional[Dict[str, Any]]:
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
    confidence = max(0.0, min(1.0, confidence))
    try:
        year = int(candidate.get("year") or default_year)
    except Exception:
        year = default_year
    return {
        "title": clean_text(str(candidate.get("title") or f"Annual Report {year}"))[:220],
        "url": url,
        "source_domain": clean_text(str(candidate.get("source_domain") or domain))[:180],
        "year": year,
        "confidence": confidence,
        "reason": clean_text(str(candidate.get("reason") or "Qwen annual report candidate."))[:600],
    }


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
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=8.0) as client:
            response = await client.head(url)
            if response.status_code in {403, 405} or response.status_code >= 500:
                response = await client.get(url, headers={"Range": "bytes=0-2048"})
            http_status = response.status_code
            mime_type = response.headers.get("content-type")
            is_reachable = response.status_code < 400
    except Exception as exc:
        validation_notes.append(f"Validation request failed: {type(exc).__name__}")

    lower_url = url.lower()
    looks_like_report = any(token in lower_url for token in ["annual", "report", "laporan", "tahunan", "ar-"]) or lower_url.endswith(".pdf")
    if not looks_like_report:
        validation_notes.append("URL does not clearly look like an annual report page or PDF.")

    is_valid = bool(allowed and is_reachable and looks_like_report)
    confidence = float(candidate.get("confidence") or 0.0)
    if allowed:
        confidence = min(1.0, confidence + 0.08)
    if is_reachable:
        confidence = min(1.0, confidence + 0.08)
    if lower_url.endswith(".pdf") or (mime_type and "pdf" in mime_type.lower()):
        confidence = min(1.0, confidence + 0.08)

    return {
        **candidate,
        "source_domain": domain or candidate.get("source_domain"),
        "confidence": round(confidence, 4),
        "http_status": http_status,
        "mime_type": mime_type,
        "is_reachable": is_reachable,
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
        "confidence": candidate.get("confidence"),
        "status": "validated" if candidate.get("is_valid") else "candidate",
        "reason": candidate.get("reason"),
        "provider": "qwen_search",
        "candidate_rank": rank,
        "http_status": candidate.get("http_status"),
        "mime_type": candidate.get("mime_type"),
        "is_valid": bool(candidate.get("is_valid")),
        "validation_notes": candidate.get("validation_notes") or [],
        "raw_payload": candidate,
        "updated_at": utc_now(),
    }


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
    user_urls = [url for url in (payload.candidate_urls or []) if clean_candidate_url(url)]
    allowed_domains = official_annual_report_domains(resolved, company_name)

    qwen_payload: Dict[str, Any] = {
        "status": "needs_search",
        "recommended_query": f"{company_name} annual report {report_year} pdf official",
        "search_queries": [
            f"{company_name} annual report {report_year} pdf official",
            f"{resolved} annual report {report_year} investor relations",
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
                )
            )
            parsed = extract_json_object(qwen_text)
            if parsed:
                qwen_payload.update(parsed)
        except Exception as exc:
            qwen_error = f"Qwen search planning failed: {type(exc).__name__}"
    else:
        qwen_error = "Qwen is not configured. Returning deterministic search queries only."

    raw_candidates: List[Dict[str, Any]] = []
    for url in user_urls:
        raw_candidates.append(
            {
                "title": f"User supplied annual report candidate {report_year}",
                "url": url,
                "source_domain": domain_from_url(url),
                "year": report_year,
                "confidence": 0.55,
                "reason": "User supplied candidate URL.",
            }
        )

    for item in qwen_payload.get("candidates") or []:
        normalized = normalize_report_candidate(item, report_year)
        if normalized:
            raw_candidates.append(normalized)

    deduped: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    for candidate in raw_candidates:
        url = candidate.get("url")
        if not url or url in seen_urls:
            continue
        deduped.append(candidate)
        seen_urls.add(url)
        if len(deduped) >= 8:
            break

    if deduped:
        validated = await asyncio.gather(
            *(validate_annual_report_candidate(candidate, allowed_domains) for candidate in deduped)
        )
    else:
        validated = []
    validated = sorted(validated, key=lambda item: (bool(item.get("is_valid")), float(item.get("confidence") or 0)), reverse=True)
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

    status = "found" if recommended and recommended.get("is_valid") else "needs_search"
    if not validated and qwen_payload.get("status") == "not_found":
        status = "not_found"

    return {
        "status": status,
        "symbol": resolved,
        "company_name": company_name,
        "report_year": report_year,
        "allowed_domains": allowed_domains,
        "recommended_source": recommended,
        "candidates": validated,
        "search_queries": qwen_payload.get("search_queries") or [],
        "recommended_query": qwen_payload.get("recommended_query"),
        "qwen_status": qwen_payload.get("status"),
        "qwen_error": qwen_error,
        "storage": storage,
        "note": "This endpoint only searches, ranks, validates, and saves annual report source metadata. It does not crawl the full site or extract tables.",
    }


def register_annual_report_routes(app) -> None:
    @app.post("/annual-report/search/{symbol}")
    async def annual_report_search_route(symbol: str, payload: Optional[AnnualReportSearchRequest] = None) -> Dict[str, Any]:
        return await search_annual_report_source(symbol, payload or AnnualReportSearchRequest())
