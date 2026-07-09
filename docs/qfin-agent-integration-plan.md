# QFin Agent Integration Plan

## Current QFin baseline

QFin already has a strong starting pattern:

- FastAPI backend on Render
- React/Vite frontend on Vercel
- Supabase for persistence
- a single main agent endpoint
- a tool-first backend with LLM narration after facts are gathered

From the current backend, the strongest existing idea is already the right one:

`facts first -> deterministic computation -> LLM explanation`

That is worth preserving.

## What the external agent repos are best at

### Best architecture patterns to borrow

#### LangChain
- Useful for standardizing tools, model adapters, and agent wiring.
- Best takeaway for QFin: interchangeable model/tool abstractions, not full framework adoption.

#### LlamaIndex
- Strongest at retrieval and document/data grounding.
- Best takeaway for QFin: build a finance-specific context layer for filings, reports, notes, and saved analyses.

#### Haystack
- Strong at explicit pipelines, routing, retrieval, and transparent context engineering.
- Best takeaway for QFin: make QFin's routing and retrieval graph visible and testable.

#### OpenAI Python
- Strongest operational reference for retries, timeouts, request IDs, async usage, streaming, and error handling.
- Best takeaway for QFin: production-grade client behavior and observability patterns.

#### CrewAI
- Strong at role-based multi-agent collaboration plus deterministic flow control.
- Best takeaway for QFin: separate agents by job, then wrap them in controlled flows.

#### Semantic Kernel / Microsoft Agent Framework
- Strong at plugin-style tools, structured orchestration, and enterprise agent design.
- Best takeaway for QFin: tool/plugin contracts and typed, structured outputs.

#### Rasa / CALM
- Strong at combining LLM flexibility with business-logic control.
- Best takeaway for QFin: business flows should constrain the agent, especially for finance actions and portfolio workflows.

#### Vercel Open Agents
- Strong at durable runs, streaming, separation of agent runtime from execution environment, and resumable workflows.
- Best takeaway for QFin: long-running analysis jobs should be resumable and not tied to one request.

### Best finance-specific patterns to borrow

#### FinRobot
- Best overall direct reference for QFin.
- Strongest ideas:
  - multi-agent equity research
  - deterministic valuation operators
  - traceable reports
  - debate-style investment reasoning
  - strict separation of numeric computation from narrative generation

#### TradingAgents
- Best direct reference for trading-style orchestration.
- Strongest ideas:
  - role-based analyst teams
  - bullish vs bearish debate
  - decision memory
  - checkpoint resume
  - reproducibility notes
  - explicit risk management and portfolio manager step

#### FinGPT
- Best reference for finance-tuned NLP, especially sentiment, headline tasks, and finance-specific data/task layers.
- Strongest takeaway for QFin: finance-specific sentiment, headline classification, and retrieval-augmented financial reasoning.

#### FinRL
- Best reference for backtesting and reinforcement-learning research workflows.
- Best takeaway for QFin: not the main chat-agent architecture, but useful for future strategy simulation and backtest modules.

## Repos that are lower priority for direct integration

### Useful to learn from, but do not add now

- Auto-GPT
  - Historically important, but too open-ended for a finance product that needs precision and guardrails.
- AgentGPT
  - Better as UX inspiration than as backend architecture.
- Transformers
  - Important for model ecosystem awareness, but not something QFin should adopt directly unless you intentionally host or fine-tune local finance models.

## Recommended decisions for QFin

### Adopt now

1. **Finance evidence packets**
   - Every finance answer should be built from a typed evidence bundle:
   - ticker resolution
   - market data snapshot
   - financial statements snapshot
   - news/headline snapshot
   - sentiment snapshot
   - valuation outputs
   - caveats and missing fields

2. **Role-based analysis flow**
   - Split the current monolithic agent into internal roles:
   - router
   - data collector
   - company analyst
   - valuation analyst
   - sentiment/news analyst
   - report synthesizer
   - risk checker

3. **Deterministic finance operators**
   - Keep calculations in code, never in model prose.
   - Start with:
   - comparables
   - simple DCF
   - quality/growth/profitability scorecards
   - risk flags

4. **Persistent memory for analyses**
   - Save prior report decisions, assumptions, and outcomes in Supabase.
   - Memory should be used as retrieved context, not hidden prompt magic.

5. **Structured outputs internally**
   - Agents should return typed JSON/Pydantic objects internally.
   - Only the final user response should become natural prose.

6. **Live headlines tool**
   - This is the broad tool that most clearly improves QFin intelligence immediately.
   - It helps with catalyst detection, market context, and event-driven analysis.

7. **Evaluation hooks**
   - Add basic scoring for:
   - ticker correctness
   - unsupported-claim rate
   - missing-caveat rate
   - source coverage
   - finance-answer structure quality

### Adopt later

1. **Bull vs bear debate mode**
   - Great for premium company reports and investment-committee style output.

2. **Checkpoint/resume for long analyses**
   - Best when QFin starts generating bigger multi-step reports or ingesting filings.

3. **RAG over filings, reports, and user uploads**
   - Best done after the evidence-packet layer is in place.

4. **Backtest and strategy-lab workflows**
   - Use FinRL-style ideas later for strategy simulation, not as the first agent upgrade.

5. **Finance-tuned local models**
   - Only worth it once you have a proven evaluation harness and a reason to beat hosted models on cost or latency.

### Skip for now

1. Adding all listed frameworks as dependencies
2. Rewriting QFin around a generic autonomous-agent loop
3. Letting the model directly compute investment numbers
4. Adding uncontrolled recursive subagent behavior

## Concrete architecture for QFin vNext

```text
User Request
  -> Intent Router
  -> Evidence Planner
  -> Tool/Data Collection
  -> Deterministic Finance Operators
  -> Specialist Analyst Roles
  -> Risk / Consistency Checker
  -> Report Composer
  -> Persist Memory + Evaluation Record
```

### Internal roles

- `router`
  - Decides whether the task is chat, finance concept, company analysis, comparison, news, or builder/backtest flow.
- `researcher`
  - Collects filings, market data, news, and registry-backed public API facts.
- `quant`
  - Runs deterministic metrics and valuation code.
- `sentiment`
  - Summarizes headlines and market mood.
- `writer`
  - Produces the final answer from approved evidence only.
- `risk`
  - Checks unsupported claims, ticker mismatch, stale data, and missing caveats.

## Priority backlog

### Phase 1

1. Introduce typed `EvidencePacket` and `AgentResult` models.
2. Add a router layer in the backend before the current Qwen call.
3. Add live headlines as a first-class tool.
4. Add a risk-check pass before final response generation.
5. Persist analysis sessions and evidence summaries in Supabase.

### Phase 2

1. Add role-based internal agents for research, quant, and writing.
2. Add debate mode for bull/bear/judge reports.
3. Add report provenance blocks and confidence labels.
4. Add evaluation logging.

### Phase 3

1. Add filing/document retrieval.
2. Add checkpoint/resume for long jobs.
3. Add backtest lab and portfolio workflows.

## Final recommendation

QFin should **not** become "an app that contains every agent framework."

It should become:

- a finance agent with strict evidence discipline
- deterministic numeric computation
- role-based internal orchestration
- persistent memory
- resumable workflows
- finance-specific evaluation

If we copy only the best ideas:

- from **FinRobot**: deterministic valuation + multi-agent finance research
- from **TradingAgents**: debate, memory, risk manager, checkpointing
- from **LlamaIndex/Haystack**: retrieval and explicit routing
- from **CrewAI/Semantic Kernel**: role separation and flow control
- from **OpenAI Python**: production reliability patterns
- from **Rasa CALM**: LLM freedom inside hard business constraints
- from **Open Agents**: durable execution

then QFin gets materially smarter without turning into framework soup.
