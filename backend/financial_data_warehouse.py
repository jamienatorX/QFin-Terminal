"""Financial data warehouse helpers for QFin Terminal.

This module is intentionally standalone so it can be wired into main.py safely later.
It provides:
- FMP provider bundle fetching
- normalized statement rows
- valuation snapshot calculations
- bank/financial institution classification
- metric coverage rows for transparent caveats
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional

import httpx

FMP_BASE_URL = "https://financialmodelingprep.com/stable"

STATEMENT_ENDPOINTS = {
    "income_statement": "income-statement",
    "balance_sheet": "balance-sheet-statement",
    "cash_flow": "cash-flow-statement",
}

FMP_BUNDLE_ENDPOINTS = {
    "profile": "profile",
    "income_statement": "income-statement",
    "balance_sheet": "balance-sheet-statement",
    "cash_flow": "cash-flow-statement",
    "key_metrics": "key-metrics",
    "ratios": "ratios",
    "key_metrics_ttm": "key-metrics-ttm",
    "ratios_ttm": "ratios-ttm",
    "enterprise_values": "enterprise-values",
    "historical_prices": "historical-price-eod/light",
}

BANK_KEYWORDS = {
    "bank",
    "banks",
    "banking",
    "financial services",
    "credit",
    "lending",
    "commercial banking",
    "regional banks",
    "capital markets",
}

STANDARD_VALUATION_FIELDS = {
    "price": ["price", "stockPrice"],
    "shares_outstanding": ["sharesOutstanding", "weightedAverageShsOut", "weightedAverageShsOutDil"],
    "market_cap": ["marketCap"],
    "enterprise_value": ["enterpriseValue"],
    "pe_ratio": ["peRatio", "priceEarningsRatio", "peRatioTTM"],
    "pb_ratio": ["pbRatio", "priceToBookRatio", "priceToBookRatioTTM"],
    "ps_ratio": ["priceToSalesRatio", "priceToSalesRatioTTM"],
    "ev_ebitda": ["enterpriseValueOverEBITDA", "evToEBITDA"],
    "dividend_yield": ["dividendYield", "dividendYieldTTM"],
    "eps": ["eps", "epsTTM", "netIncomePerShareTTM"],
    "book_value_per_share": ["bookValuePerShare", "bookValuePerShareTTM"],
    "revenue": ["revenue", "revenueTTM"],
    "net_income": ["netIncome", "netIncomeTTM"],
    "ebitda": ["ebitda", "ebitdaTTM"],
    "total_equity": ["totalStockholdersEquity", "totalEquity"],
    "total_debt": ["totalDebt", "netDebt"],
    "cash_and_equivalents": ["cashAndCashEquivalents", "cashAndShortTermInvestments"],
}

BANK_KPI_FIELDS = {
    "nim": ["netInterestMargin", "netInterestMarginTTM"],
    "roe": ["returnOnEquity", "returnOnEquityTTM"],
    "roa": ["returnOnAssets", "returnOnAssetsTTM"],
    "cost_to_income_ratio": ["costToIncomeRatio"],
    "loan_to_deposit_ratio": ["loanToDepositRatio"],
    "npl_ratio": ["nonPerformingLoanRatio", "nplRatio"],
    "net_interest_income": ["netInterestIncome"],
    "total_loans": ["totalLoans"],
    "total_deposits": ["totalDeposits", "customerDeposits"],
    "total_assets": ["totalAssets"],
    "total_equity": ["totalStockholdersEquity", "totalEquity"],
    "net_income": ["netIncome"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fmp_api_key() -> str:
    return os.getenv("FMP_API_KEY", "").strip()


def fmp_is_configured() -> bool:
    return bool(fmp_api_key())


def to_decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def first_numeric(*records: Dict[str, Any], keys: Iterable[str]) -> Optional[Decimal]:
    for record in records:
        if not isinstance(record, dict):
            continue
        for key in keys:
            value = to_decimal(record.get(key))
            if value is not None:
                return value
    return None


def first_text(*records: Dict[str, Any], keys: Iterable[str]) -> Optional[str]:
    for record in records:
        if not isinstance(record, dict):
            continue
        for key in keys:
            value = record.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return None


async def fmp_get_json(client: httpx.AsyncClient, endpoint: str, params: Dict[str, Any]) -> Any:
    key = fmp_api_key()
    if not key:
        raise RuntimeError("FMP_API_KEY is not configured.")
    response = await client.get(
        f"{FMP_BASE_URL}/{endpoint.lstrip('/')}",
        params={**params, "apikey": key},
    )
    response.raise_for_status()
    return response.json()


async def fetch_fmp_bundle(symbol: str, limit: int = 5) -> Dict[str, Any]:
    """Fetch a broad FMP data bundle for one symbol.

    The returned bundle is raw provider data. Normalize before saving to Supabase.
    """
    if not fmp_is_configured():
        return {
            "symbol": symbol,
            "provider": "fmp",
            "status": "missing_api_key",
            "fetched_at": utc_now(),
            "data": {},
        }

    timeout_seconds = float(os.getenv("FINANCIAL_DATA_TIMEOUT_SECONDS", "45"))
    bundle: Dict[str, Any] = {}
    warnings: List[str] = []

    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
        for name, endpoint in FMP_BUNDLE_ENDPOINTS.items():
            params: Dict[str, Any] = {"symbol": symbol}
            if name in {"income_statement", "balance_sheet", "cash_flow", "key_metrics", "ratios", "enterprise_values"}:
                params["limit"] = limit
            try:
                bundle[name] = await fmp_get_json(client, endpoint, params)
            except Exception as exc:  # Keep bundle partially useful.
                bundle[name] = []
                warnings.append(f"{name}: {type(exc).__name__}")

    return {
        "symbol": symbol,
        "provider": "fmp",
        "status": "partial" if warnings else "success",
        "warnings": warnings,
        "fetched_at": utc_now(),
        "data": bundle,
    }


def normalize_profile(symbol: str, bundle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    profiles = bundle.get("data", {}).get("profile") or []
    profile = profiles[0] if isinstance(profiles, list) and profiles else {}
    if not isinstance(profile, dict):
        return None
    company_name = first_text(profile, keys=["companyName", "companyNameLong", "name"]) or symbol
    return {
        "symbol": symbol,
        "yahoo_symbol": symbol,
        "company_name": company_name,
        "exchange": first_text(profile, keys=["exchange", "exchangeShortName"]),
        "market": first_text(profile, keys=["exchangeShortName"]),
        "country": first_text(profile, keys=["country"]),
        "currency": first_text(profile, keys=["currency", "reportedCurrency"]),
        "sector": first_text(profile, keys=["sector"]),
        "industry": first_text(profile, keys=["industry"]),
        "website": first_text(profile, keys=["website"]),
        "description": first_text(profile, keys=["description"]),
        "provider_payload": profile,
        "source": "fmp",
        "source_confidence": 0.85,
        "retrieved_at": utc_now(),
    }


def normalize_statement_rows(symbol: str, bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    data = bundle.get("data", {})
    profile = normalize_profile(symbol, bundle) or {}
    company_name = profile.get("company_name")

    for statement_type, endpoint_name in STATEMENT_ENDPOINTS.items():
        records = data.get(statement_type) or []
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            year_raw = record.get("calendarYear") or str(record.get("date") or "")[:4]
            try:
                fiscal_year = int(year_raw)
            except Exception:
                continue
            currency = record.get("reportedCurrency") or profile.get("currency")
            period = str(record.get("period") or "FY")
            period_type = "annual" if period.upper() == "FY" else "quarterly"
            period_end_date = str(record.get("date") or "")[:10] or None

            for metric_name, metric_value in record.items():
                if metric_name in {"symbol", "date", "calendarYear", "period", "reportedCurrency", "cik", "fillingDate", "acceptedDate", "link", "finalLink"}:
                    continue
                numeric_value = to_decimal(metric_value)
                if numeric_value is None:
                    continue
                output.append(
                    {
                        "symbol": symbol,
                        "company_name": company_name,
                        "fiscal_year": fiscal_year,
                        "fiscal_period": period,
                        "period_type": period_type,
                        "period_end_date": period_end_date,
                        "statement_type": statement_type,
                        "metric_name": metric_name,
                        "metric_label": metric_name.replace("_", " "),
                        "metric_value": str(numeric_value),
                        "metric_unit": "currency",
                        "currency": currency,
                        "source": "fmp",
                        "source_url": record.get("finalLink") or record.get("link"),
                        "source_confidence": 0.85,
                        "provider_payload": record,
                        "retrieved_at": utc_now(),
                    }
                )
    return output


def calculate_valuation_snapshot(symbol: str, bundle: Dict[str, Any]) -> Dict[str, Any]:
    data = bundle.get("data", {})
    profile = (data.get("profile") or [{}])[0] if isinstance(data.get("profile"), list) else {}
    key_metrics_ttm = (data.get("key_metrics_ttm") or [{}])[0] if isinstance(data.get("key_metrics_ttm"), list) else {}
    ratios_ttm = (data.get("ratios_ttm") or [{}])[0] if isinstance(data.get("ratios_ttm"), list) else {}
    enterprise_values = (data.get("enterprise_values") or [{}])[0] if isinstance(data.get("enterprise_values"), list) else {}
    income_ttm = (data.get("income_statement") or [{}])[0] if isinstance(data.get("income_statement"), list) else {}
    balance_latest = (data.get("balance_sheet") or [{}])[0] if isinstance(data.get("balance_sheet"), list) else {}

    records = [profile, key_metrics_ttm, ratios_ttm, enterprise_values, income_ttm, balance_latest]
    values: Dict[str, Optional[Decimal]] = {}
    for output_name, keys in STANDARD_VALUATION_FIELDS.items():
        values[output_name] = first_numeric(*records, keys=keys)

    price = values.get("price")
    shares = values.get("shares_outstanding")
    market_cap = values.get("market_cap") or ((price * shares) if price is not None and shares is not None else None)
    total_debt = values.get("total_debt")
    cash = values.get("cash_and_equivalents")
    enterprise_value = values.get("enterprise_value")
    if enterprise_value is None and market_cap is not None:
        enterprise_value = market_cap + (total_debt or Decimal("0")) - (cash or Decimal("0"))

    revenue = values.get("revenue")
    net_income = values.get("net_income")
    total_equity = values.get("total_equity")
    ebitda = values.get("ebitda")
    pe_ratio = values.get("pe_ratio") or ((market_cap / net_income) if market_cap and net_income else None)
    pb_ratio = values.get("pb_ratio") or ((market_cap / total_equity) if market_cap and total_equity else None)
    ps_ratio = values.get("ps_ratio") or ((market_cap / revenue) if market_cap and revenue else None)
    ev_ebitda = values.get("ev_ebitda") or ((enterprise_value / ebitda) if enterprise_value and ebitda else None)

    filled_metrics = [market_cap, pe_ratio, pb_ratio, ps_ratio, ev_ebitda]
    data_quality = "complete" if all(value is not None for value in filled_metrics) else "partial"

    def out(value: Optional[Decimal]) -> Optional[str]:
        return str(value) if value is not None else None

    return {
        "symbol": symbol,
        "snapshot_date": date.today().isoformat(),
        "fiscal_period": "TTM",
        "price": out(price),
        "shares_outstanding": out(shares),
        "market_cap": out(market_cap),
        "total_debt": out(total_debt),
        "cash_and_equivalents": out(cash),
        "enterprise_value": out(enterprise_value),
        "revenue": out(revenue),
        "ebitda": out(ebitda),
        "net_income": out(net_income),
        "total_equity": out(total_equity),
        "eps": out(values.get("eps")),
        "book_value_per_share": out(values.get("book_value_per_share")),
        "pe_ratio": out(pe_ratio),
        "pb_ratio": out(pb_ratio),
        "ps_ratio": out(ps_ratio),
        "ev_ebitda": out(ev_ebitda),
        "dividend_yield": out(values.get("dividend_yield")),
        "currency": first_text(profile, income_ttm, balance_latest, keys=["currency", "reportedCurrency"]),
        "calculation_method": "fmp_provider_or_calculated",
        "source": "fmp",
        "source_confidence": 0.85,
        "data_quality": data_quality,
        "notes": "Valuation fields are provider-returned where available and calculated from market cap, income statement, and balance sheet where needed.",
        "provider_payload": {
            "profile": profile,
            "key_metrics_ttm": key_metrics_ttm,
            "ratios_ttm": ratios_ttm,
            "enterprise_values": enterprise_values,
        },
        "retrieved_at": utc_now(),
    }


def is_financial_institution(profile: Dict[str, Any]) -> bool:
    text = " ".join(
        str(profile.get(key) or "")
        for key in ("company_name", "sector", "industry", "description")
    ).lower()
    return any(keyword in text for keyword in BANK_KEYWORDS)


def calculate_bank_kpi_row(symbol: str, bundle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = bundle.get("data", {})
    profile = normalize_profile(symbol, bundle) or {"symbol": symbol, "company_name": symbol}
    if not is_financial_institution(profile):
        return None

    ratios = (data.get("ratios") or [{}])[0] if isinstance(data.get("ratios"), list) else {}
    ratios_ttm = (data.get("ratios_ttm") or [{}])[0] if isinstance(data.get("ratios_ttm"), list) else {}
    income = (data.get("income_statement") or [{}])[0] if isinstance(data.get("income_statement"), list) else {}
    balance = (data.get("balance_sheet") or [{}])[0] if isinstance(data.get("balance_sheet"), list) else {}
    records = [ratios_ttm, ratios, income, balance]

    year_raw = income.get("calendarYear") or balance.get("calendarYear") or datetime.now().year
    try:
        fiscal_year = int(year_raw)
    except Exception:
        fiscal_year = datetime.now().year

    row: Dict[str, Any] = {
        "symbol": symbol,
        "fiscal_year": fiscal_year,
        "fiscal_period": str(income.get("period") or balance.get("period") or "FY"),
        "period_type": "annual",
        "period_end_date": str(income.get("date") or balance.get("date") or "")[:10] or None,
        "currency": profile.get("currency") or income.get("reportedCurrency") or balance.get("reportedCurrency"),
        "source": "fmp",
        "source_confidence": 0.75,
        "provider_payload": {"ratios": ratios, "ratios_ttm": ratios_ttm, "income": income, "balance": balance},
        "retrieved_at": utc_now(),
    }

    for output_name, keys in BANK_KPI_FIELDS.items():
        value = first_numeric(*records, keys=keys)
        row[output_name] = str(value) if value is not None else None
    return row


def build_metric_coverage(symbol: str, years: List[int], statement_rows: List[Dict[str, Any]], valuation: Dict[str, Any], bank_kpi: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    available_statements = {
        (int(row["fiscal_year"]), row["statement_type"])
        for row in statement_rows
        if row.get("fiscal_year") and row.get("statement_type")
    }
    valuation_metrics = ["pe_ratio", "pb_ratio", "ps_ratio", "ev_ebitda", "market_cap"]
    bank_metrics = ["nim", "roe", "roa", "npl_ratio", "loan_to_deposit_ratio", "casa_ratio", "car"]
    rows: List[Dict[str, Any]] = []

    for fiscal_year in years:
        for statement_type in ["income_statement", "balance_sheet", "cash_flow"]:
            status = "available" if (fiscal_year, statement_type) in available_statements else "missing"
            rows.append(
                {
                    "symbol": symbol,
                    "fiscal_year": fiscal_year,
                    "fiscal_period": "FY",
                    "metric_group": "financial_statement",
                    "metric_name": statement_type,
                    "status": status,
                    "source": "fmp" if status == "available" else None,
                    "source_confidence": 0.85 if status == "available" else None,
                    "note": None if status == "available" else "Provider did not return this statement for the period.",
                }
            )

    current_year = datetime.now().year
    for metric_name in valuation_metrics:
        status = "available" if valuation.get(metric_name) is not None else "missing"
        rows.append(
            {
                "symbol": symbol,
                "fiscal_year": current_year,
                "fiscal_period": "TTM",
                "metric_group": "valuation",
                "metric_name": metric_name,
                "status": status,
                "source": "fmp" if status == "available" else None,
                "source_confidence": 0.85 if status == "available" else None,
                "note": None if status == "available" else "Could not calculate because one or more required inputs were missing.",
            }
        )

    if bank_kpi:
        for metric_name in bank_metrics:
            status = "available" if bank_kpi.get(metric_name) is not None else "missing"
            rows.append(
                {
                    "symbol": symbol,
                    "fiscal_year": int(bank_kpi.get("fiscal_year") or current_year),
                    "fiscal_period": bank_kpi.get("fiscal_period") or "FY",
                    "metric_group": "bank_kpi",
                    "metric_name": metric_name,
                    "status": status,
                    "source": "fmp" if status == "available" else None,
                    "source_confidence": 0.75 if status == "available" else None,
                    "note": None if status == "available" else "Bank KPI not returned by provider; use annual-report/manual override if needed.",
                }
            )
    else:
        rows.append(
            {
                "symbol": symbol,
                "fiscal_year": current_year,
                "fiscal_period": "TTM",
                "metric_group": "bank_kpi",
                "metric_name": "bank_specific_metrics",
                "status": "not_applicable",
                "source": None,
                "source_confidence": None,
                "note": "Company was not classified as a bank or financial institution.",
            }
        )

    return rows
