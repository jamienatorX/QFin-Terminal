# QFin Answer Quality Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract QFin's user-facing finance-answer policy from the FastAPI entrypoint and strengthen its provider-independent output contract.

**Architecture:** Create one deep `answer_quality` module with a small normalization/finalization interface. Keep `main.py` as the composition root and preserve its existing imports so routes and tests remain compatible.

**Tech Stack:** Python 3, FastAPI, Pydantic, `unittest`

## Global Constraints

- Do not change public API routes or response schemas.
- Do not change financial claims, currencies, units, or reporting periods.
- Do not expose provider names, routing details, diagnostics, or methodology unless requested.
- Use test-driven development and run the full backend suite before publication.

---

### Task 1: Answer-quality contract

**Files:**
- Create: `backend/tests/test_answer_quality.py`
- Create: `backend/answer_quality.py`

**Interfaces:**
- Produces: `user_requests_methodology(query)`, `normalize_finance_answer(content, route_kind, preserve_methodology=False)`, and `finalize_finance_answer(content, missing_data=(), preserve_methodology=False)`.

- [ ] **Step 1: Write failing tests** for route headings, hidden diagnostics, methodology policy, empty output, duplicate caveats, and legitimate `Q` words.
- [ ] **Step 2: Run `python -m unittest tests.test_answer_quality -v`** and confirm failure because `answer_quality` does not exist.
- [ ] **Step 3: Implement the minimal standalone policy module** using deterministic text transformations only.
- [ ] **Step 4: Run the focused test** and confirm all answer contract cases pass.

### Task 2: Composition-root integration

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/tests/test_routing.py`

**Interfaces:**
- Consumes: the three functions from `backend/answer_quality.py`.
- Produces: the existing `main.normalize_finance_answer`, `main.user_requests_methodology`, and `main.finalize_agent_content` behavior used by routes and tests.

- [ ] **Step 1: Add a failing routing test** proving finalization delegates missing-data caveats without exposing risk warnings.
- [ ] **Step 2: Run the focused routing test** and confirm the expected failure.
- [ ] **Step 3: Import the policy functions into `main.py`, remove duplicated implementations, and adapt `finalize_agent_content` to pass `review.missing_data`.**
- [ ] **Step 4: Run focused and full backend tests.**

### Task 3: Frontend stable boundaries

**Files:**
- Create: `frontend/src/domain/types.ts`
- Create: `frontend/src/lib/personalShelf.ts`
- Modify: `frontend/src/main.tsx`

**Interfaces:**
- Produces: shared QFin domain types and `readPersonalShelf`/`writePersonalShelf`.
- Consumes: browser `localStorage` under the existing key and the unchanged shelf schema.

- [ ] **Step 1: Move shared type declarations without changing their fields.**
- [ ] **Step 2: Move shelf serialization behind the persistence module.**
- [ ] **Step 3: Update imports in `main.tsx` and remove duplicate declarations.**
- [ ] **Step 4: Run `npm run build` and resolve only extraction-related type errors.**

### Task 4: Final verification and publication

**Files:**
- Review all changed files.

- [ ] **Step 1: Run all backend tests from `backend`.**
- [ ] **Step 2: Run the frontend production build.**
- [ ] **Step 3: Inspect the diff for public API, visual copy, styling, or secret changes.**
- [ ] **Step 4: Publish the verified branch to GitHub and open a pull request.**
