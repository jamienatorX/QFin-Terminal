# QFin Financial Data Warehouse

QFin should not depend on yfinance as the database. yfinance, Finnhub, FMP, NewsAPI, and uploaded annual reports should be treated as data providers. Supabase is the reusable warehouse/cache.

## New live Supabase tables

| Table | Purpose |
|---|---|
| `qfin_company_profiles` | Canonical company profile, sector, country, currency, and provider payload cache |
| `qfin_market_prices_daily` | Historical daily OHLCV price cache |
| `qfin_financial_statements` | Normalized income statement, balance sheet, and cash flow metrics by year/period |
| `qfin_valuation_snapshots` | P/E, P/B, P/S, EV/EBITDA, market cap, enterprise value, and calculated valuation metrics |
| `qfin_bank_kpis` | Bank-specific KPIs such as loans, deposits, NIM, ROE, ROA, NPL, LDR, CASA, CAR |
| `qfin_data_source_runs` | Audit log for every provider retrieval run |
| `qfin_metric_coverage` | Data coverage map: available, missing, estimated, manual, or not applicable |
| `qfin_manual_overrides` | User/admin-entered numbers from annual reports, PDFs, or official filings |

## Correct provider order

```text
1. Supabase warehouse/cache
2. Manual override / official uploaded report
3. Financial Modeling Prep API
4. Finnhub API
5. yfinance
6. Deterministic fallback only for UI simulation, never for real valuation
```

## Analysis flow

```text
User asks: Analyze BBCA
↓
Resolve symbol: BBCA.JK
↓
Check qfin_company_profiles, qfin_financial_statements, qfin_valuation_snapshots, qfin_bank_kpis
↓
If missing, run provider ingestion
↓
Normalize every metric into Supabase
↓
Calculate valuation ratios if provider does not return them
↓
Create qfin_metric_coverage rows
↓
Generate answer with data coverage table and caveats
```

## Valuation calculation rules

For normal operating companies:

```text
Market Cap = Share Price × Shares Outstanding
P/E = Market Cap / Net Income
P/B = Market Cap / Total Equity
P/S = Market Cap / Revenue
Enterprise Value = Market Cap + Total Debt + Preferred Equity + Minority Interest - Cash
EV/EBITDA = Enterprise Value / EBITDA
```

For banks and financial institutions:

```text
Primary: P/B, P/E, ROE, ROA, NIM, loan growth, deposit growth, NPL, LDR, CASA, CAR
Avoid overemphasis on EV/EBITDA and normal operating-cash-flow interpretation
```

## Bank analysis rule

When the company is a bank, QFin should automatically add this caveat:

```text
Because this is a financial institution, operating cash flow is heavily affected by deposit and lending movements. P/B, P/E, ROE, NIM, asset quality, liquidity, and capital ratios are more meaningful than EV/EBITDA or standard industrial cash-flow interpretation.
```

## Data coverage table in every deep report

Every full company analysis should include a compact coverage table like this:

| Metric group | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|
| Income statement | Missing | Available | Available | Available | Available |
| Balance sheet | Missing | Available | Available | Available | Available |
| Cash flow | Missing | Available | Available | Available | Available |
| Valuation | Partial | Available | Available | Available | Partial |
| Bank KPIs | Missing | Partial | Partial | Partial | Partial |

## Backend integration still needed

The live database foundation is ready. The next code step is to wire `backend/main.py` or a new service module to:

1. Read from Supabase warehouse before calling providers.
2. Add FMP provider ingestion using `FMP_API_KEY`.
3. Save normalized statement rows into `qfin_financial_statements`.
4. Save valuation metrics into `qfin_valuation_snapshots`.
5. Save bank metrics into `qfin_bank_kpis`.
6. Save missing/available status into `qfin_metric_coverage`.
7. Attach coverage summaries to the agent evidence packet.

## Why this fixes the BBCA problem

If 2021 is missing from yfinance, QFin can now store that fact in `qfin_metric_coverage`. If the user uploads BBCA's annual report, extracted 2021 numbers can be saved as `manual` or `approved` metrics instead of being lost after one chat. If valuation ratios are missing, QFin can calculate P/E and P/B from price, shares, net income, and equity, then store the calculated snapshot for reuse.
