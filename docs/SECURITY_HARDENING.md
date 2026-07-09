# QFin Terminal Security Hardening

This checklist documents the production-hardening work for QFin Terminal.

## Completed in Supabase

- Enabled RLS on `qfin_forum_threads` and `qfin_builder_models`.
- Added `owner_id` columns to forum threads and builder models.
- Added ownership-based read/write/delete policies.
- Rewrote RLS policies to use `(select auth.uid())` for better planner behavior.
- Added missing foreign-key indexes for community posts and model templates.
- Removed the duplicate `qfin_symbol_master` symbol index.
- Moved `pg_trgm` out of the `public` schema into `extensions`.

## Backend changes still required in `backend/main.py`

The current backend uses the Supabase service role key for REST calls. This is correct for trusted server operations, but it means RLS is bypassed unless the backend verifies the user itself.

Before production launch, add these changes:

1. Read `ALLOWED_ORIGINS` from env and replace `allow_origins=["*"]`.
2. Verify the Supabase JWT from the `Authorization: Bearer <token>` header on write routes.
3. Pass the verified user id into writes as `owner_id`.
4. Keep service role access server-only.
5. Return generic error messages to the frontend and log detailed exceptions server-side.
6. Add rate limiting for chat, forum, votes, and builder endpoints.

## Suggested production route protection

Protect these routes first:

- `POST /community/forum`
- `POST /community/forum/{thread_id}/vote`
- `POST /community/models`
- `POST /builder/save-private`
- `POST /builder/run-private`
- `POST /builder/publish`
- `POST /symbols/seed`
- `GET /agent/sessions/recent`

## Recommended auth flow

```text
Supabase Auth login in frontend
→ frontend sends Authorization header to FastAPI
→ FastAPI verifies user via Supabase Auth
→ FastAPI writes owner_id = verified user id
→ Supabase service role stays only in backend env
```

## Error handling rule

Do not send raw exception strings to the browser. Use this pattern:

```python
logger.exception("agent_chat_failed")
return {
    "id": "qfin-agent-error",
    "role": "assistant",
    "content": "QFin could not complete that reply right now. Please retry.",
    "answer": "QFin could not complete that reply right now. Please retry.",
    "data": {"error": "internal_error"},
}
```
