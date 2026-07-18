# QFin Structure and Answer Quality Design

## Goal

Improve QFin's maintainability and finance-answer consistency without changing its visual design, public API routes, or stored-data formats.

## Current pressure

- `backend/main.py` is the composition root, route layer, data orchestration layer, finance-analysis pipeline, and answer formatter in one file.
- `frontend/src/main.tsx` owns domain types, persistence, API calls, rendering helpers, and every screen.
- Finance output passes through several providers, so headings and internal diagnostic text can drift even when the underlying facts are correct.
- Existing backend tests provide a strong regression baseline, but the answer-quality policy is not exposed as an independent module interface.

## Chosen approach

Use staged deep-module extraction rather than a rewrite.

The first seam is a backend `answer_quality` module. Its small public interface accepts model text plus route context and returns normalized user-facing Markdown. It hides provider cleanup, heading repair, boilerplate removal, methodology policy, and data-gap presentation. `backend/main.py` remains compatible by importing and re-exporting the existing function names.

The second seam is the frontend API/persistence boundary. Shared domain types, HTTP requests, and personal-shelf storage move out of `main.tsx`. Screens keep their current behavior and styling while depending on focused interfaces.

## Backend interface

```python
def user_requests_methodology(query: str) -> bool: ...

def normalize_finance_answer(
    content: str,
    route_kind: str,
    preserve_methodology: bool = False,
) -> str: ...

def finalize_finance_answer(
    content: str,
    missing_data: Sequence[str] = (),
    preserve_methodology: bool = False,
) -> str: ...
```

The module must:

- preserve factual claims and supplied units;
- remove `Q`, `Direct answer`, and provider preambles;
- use route-specific QFin opening headings;
- convert known bold pseudo-headings into Markdown headings;
- remove methodology unless explicitly requested;
- remove generic verdict boilerplate and server diagnostics;
- show only genuine missing-data caveats;
- avoid duplicate opening headings and caveat sections;
- preserve legitimate phrases such as `Quarterly` and `Q&A`.

## Frontend interfaces

```typescript
export interface QFinApi {
  chat(request: AgentRequest): Promise<AgentReply>;
  upload(request: UploadRequest): Promise<AgentReply>;
  // Existing community and builder operations retain their current payloads.
}

export function readPersonalShelf(): PersonalShelf;
export function writePersonalShelf(shelf: PersonalShelf): void;
```

The first frontend extraction will move only stable, reusable boundaries. UI state and rendering remain in place until the extracted modules compile and the production build passes.

## Behavior improvements

- Provider-independent response formatting.
- Internal model, routing, warning, and fallback details stay server-side.
- Finance answers retain a decisive QFin thesis and route-appropriate sections.
- Missing data is stated once and does not replace the useful analysis.
- Malformed or empty model output falls back safely instead of becoming a blank chat response.
- No visual redesign is included.

## Verification

- Add answer-quality contract tests before production changes and observe them fail.
- Run the focused tests after each extraction.
- Run all backend tests.
- Run the frontend TypeScript/Vite production build.
- Review the final diff for accidental route, copy, or styling changes.

## Rollout

1. Extract and strengthen backend answer quality.
2. Verify all backend behavior.
3. Extract low-risk frontend boundaries.
4. Verify the production frontend build.
5. Publish one reviewable GitHub branch and pull request.
