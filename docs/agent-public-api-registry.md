# QFin Public API Registry

QFin should not blindly connect to every API listed in public API directories. Large public API lists are useful discovery maps, but many entries are unreliable, rate-limited, deprecated, unauthenticated, or unrelated to QFin's product promise.

The safer architecture is:

1. Keep finance as QFin's strongest mode.
2. Add a curated registry of useful APIs by domain.
3. Automatically call only stable, no-key APIs for general questions.
4. Keep API-key services explicit and environment-variable gated.
5. Let Qwen narrate results after tools return facts.

## Active No-Key Tools

- Wikipedia REST API: general factual summaries.
- REST Countries: country, population, capital, currency, region, timezone.
- Open-Meteo: geocoding and current weather.
- Open Library: books, authors, publications, ISBN lookup.
- Yahoo Finance via yfinance: finance fallback for public companies and backtests.

## Finance And Macro Candidates

- Finnhub: already supported when `FINNHUB_API_KEY` is configured.
- SEC EDGAR: best next source for US filing-backed financial reports.
- FRED: best next source for rates, inflation, employment, GDP, and macro charts.
- World Bank Indicators: best next source for country macro comparisons.
- GDELT: candidate for broader global news and event monitoring.

## Runtime Behavior

For general non-finance questions, `/agent/chat` now tries lightweight public-data enrichment first. If a public API returns facts, Qwen receives those facts and writes a normal answer. If no public facts are found, Qwen answers normally using its model knowledge and runtime date context.

For finance questions, QFin still uses the finance-specific route first. That keeps company analysis, comparisons, news, and model-builder behavior disciplined and avoids random API noise.

The API registry is exposed at:

```text
GET /agent/api-registry
```

## Source References

- Public APIs directory: https://github.com/public-apis/public-apis
- Vercel open-agents reference: https://github.com/vercel-labs/open-agents

The public APIs directory is used as a category and source-discovery reference. The open-agents repo is used as an architecture reference for separating agent orchestration, tools, and deployable surfaces.
