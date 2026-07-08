# QFin Agent Architecture Research

This note captures the useful patterns from the open-source agent projects James flagged for QFin Terminal. The goal is not to copy another project wholesale. QFin should stay a focused finance agent: simple chat UI, backend-owned routing, curated tools, Qwen as final narrator, and clear evidence boundaries.

## Sources Reviewed

- Vercel AI SDK: https://github.com/vercel/ai
- elizaOS: https://github.com/elizaOS/eliza
- LangChain Open SWE: https://github.com/langchain-ai/open-swe
- UI-TARS Desktop: https://github.com/bytedance/UI-TARS-desktop
- nanobot: https://github.com/HKUDS/nanobot
- OpenMontage: https://github.com/calesthio/OpenMontage
- Continue: https://github.com/continuedev/continue
- system_prompts_leaks: https://github.com/asgeirtj/system_prompts_leaks

## Safe Takeaways

1. Keep the model/provider layer swappable.
   Vercel AI SDK uses a provider-agnostic architecture and a tool-loop agent pattern. QFin should keep Qwen behind `qwen_client.py` and avoid frontend-specific model instructions so the provider can change later without rewiring the app.

2. Let tools gather facts, then let the model narrate.
   The clean pattern is: user asks -> backend routes -> tools fetch facts -> Qwen writes the final answer. The frontend should only send the user message and render the answer.

3. Curate tools instead of adding everything.
   Open SWE emphasizes a small focused toolset over tool sprawl. QFin should prioritize finance tools that matter: ticker resolution, market data, fundamentals, news, reports, forum, model builder, and backtests.

4. Persist useful context.
   nanobot and elizaOS both emphasize long-running workflows, memory, and ownership. For QFin this maps to Supabase-backed reports, saved models, watchlists, forum posts, and possibly user-specific analyst preferences later.

5. Expose tool progress to the UI only when useful.
   Vercel AI SDK and UI-TARS show that agent UIs work best when they can display tool states, progress, and final artifacts. QFin can later show cards such as "Resolving ticker", "Fetching fundamentals", "Running backtest", and "Writing report" without exposing hidden prompt text.

6. Use reproducible pipelines for artifact-heavy work.
   OpenMontage treats outputs as pipelines with costs, assets, approvals, and replayable runs. QFin's model builder should follow that idea: each model run should save assumptions, ticker, data window, stats, chart series, trade log, and verdict.

7. Do not copy leaked proprietary prompts.
   The `system_prompts_leaks` repository indexes extracted prompts from many commercial assistants. QFin should not copy those prompts. The safe lesson is structural only: clear role, tool boundaries, uncertainty policy, output style, and refusal/limitation rules.

## QFin Integration Direction

Current backend direction:

- `/agent/chat` remains the single frontend chat route.
- The backend classifies the user request as casual, time, news, comparison, company, finance concept, or general.
- For finance routes, backend tools fetch data first.
- Qwen receives the user request plus structured backend facts.
- Qwen writes the final response and must not reveal hidden route names, modes, or backend prompt text.

Near-term upgrades:

- Add explicit tool progress events for frontend rendering.
- Store generated reports and backtests in Supabase.
- Add a richer model-run schema: inputs, ticker, data source, equity curve, drawdown, trades, risk metrics, warnings, and author.
- Add a finance data adapter layer so Finnhub, Yahoo, SEC, IDX, SGX, Bursa, and other regional sources can be swapped without changing agent logic.
- Add evaluation prompts and test cases for common failures: ticker substitution, missing fundamentals, casual chat, thank-you messages, comparisons, news categories, and current date questions.

## Prompt Contract Added To Backend

QFin's system prompt now includes:

- natural general chat behavior
- finance analyst behavior
- hidden route/tool protection
- no hidden mode text in user-visible answers
- no ticker substitution
- no fabricated figures, dates, filings, sources, prices, ratios, or news
- missing-data handling
- clean markdown and direct verdicts
- runtime date/time context for ordinary date-sensitive questions

This makes QFin closer to a real AI analyst agent: Qwen can speak naturally, but finance claims must stay grounded in backend facts.
