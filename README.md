# QFin Terminal

QFin Terminal is an AI finance learning platform built with Codex for OpenAI Build Week. It helps users understand companies, markets, reports, and trading models through chat, file analysis, community discussion, and an interactive model builder.

The app has four main layers:

```text
Frontend: React / Vite website deployed on Vercel
Backend: FastAPI service deployed on Render
AI: GLM 5.2 / GLM 5.1 through a provider-compatible backend route
Database: Supabase Postgres behind the backend
```

## Repository structure

```text
QFin-Terminal
├── backend
├── frontend
├── supabase
├── README.md
├── render.yaml
├── vercel.json
├── .gitignore
└── LICENSE
```

## What works

- Frontend opens locally at `http://localhost:5173`
- Frontend fallback backend is `https://qfin-terminal.onrender.com`
- Chat and company analysis call FastAPI `POST /agent/chat/stream`
- The frontend reads chat responses as plain text with `response.text()`
- Community news calls `/community/news/{category}` and falls back to `/news/{category}`
- Community forum threads, votes, and builder models persist through Supabase when configured
- Backend opens locally at `http://127.0.0.1:8000`
- `/`, `/health`, `/docs`, `/agent/chat/stream`, `/community/news/{category}`, `/community/forum`, and `/community/models` work
- The AI provider and Supabase are called only from the backend
- Reports & Watchlist lets users save conversations, topics, private models, and private model runs
- Builder models can be saved privately, run privately, or published to the public model gallery

## AI model routing

QFin does not use the strongest model for every request. The backend routes requests by task so the app stays faster and cheaper:

```text
Deep financial report / analyst agent  -> GLM 5.2
Quick summary / cheaper backup         -> GLM 5.1
News and general chat                   -> GLM 5.2 with GLM 5.1 fallback
```

If the primary model times out or returns a temporary API error, the backend automatically tries faster backup models. Authentication errors still stop immediately because they mean the API key or base URL is wrong.

## Local backend setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/docs
```

## Backend environment variables

Create this file locally:

```text
backend/.env
```

Add:

```env
AI_PROVIDER_API_KEY=your_provider_api_key
AI_PROVIDER_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
AI_PROVIDER_MODEL_DEEP=glm-5.2
AI_PROVIDER_MODEL_FAST=glm-5.2
AI_PROVIDER_MODEL_FLASH=glm-5.1
AI_PROVIDER_MODEL_VISION=glm-5.2
AI_PROVIDER_NEWS_MODEL=glm-5.2
AI_PROVIDER_TIMEOUT_SECONDS=45
AI_PROVIDER_TOTAL_TIMEOUT_SECONDS=75
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_secret_or_service_role_key
FINNHUB_API_KEY=your_finnhub_api_key
FMP_API_KEY=your_fmp_api_key
NEWSAPI_KEY=your_newsapi_key
```

Do not commit `.env` to GitHub.

## Supabase setup

Run the SQL in:

```text
supabase/schema.sql
```

This creates the forum and builder persistence tables:

- `public.qfin_forum_threads`
- `public.qfin_builder_models`
- `public.qfin_reports`

The backend uses the Supabase service role key, so the browser never talks to these tables directly.

## Local frontend setup

```powershell
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

To connect the frontend to a deployed backend, create:

```text
frontend/.env.local
```

Add:

```env
VITE_API_BASE_URL=https://qfin-terminal.onrender.com
```

Restart the frontend after changing `.env.local`.

## Vercel frontend deployment

This repo includes `vercel.json` so Vercel can build the app from the repository root.

Use these settings if configuring manually:

```text
Install Command: cd frontend && npm install
Build Command: cd frontend && npm run build
Output Directory: frontend/dist
```

Set this environment variable in Vercel:

```env
VITE_API_BASE_URL=https://qfin-terminal.onrender.com
```

## Render backend deployment

This repo includes `render.yaml`.

For manual Render setup, use:

```text
Root Directory: backend
Build Command: pip install -r requirements.txt
Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
```

Set these environment variables in Render:

```env
AI_PROVIDER_API_KEY=your_provider_api_key
AI_PROVIDER_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
AI_PROVIDER_MODEL_DEEP=glm-5.2
AI_PROVIDER_MODEL_FAST=glm-5.2
AI_PROVIDER_MODEL_FLASH=glm-5.1
AI_PROVIDER_MODEL_VISION=glm-5.2
AI_PROVIDER_NEWS_MODEL=glm-5.2
AI_PROVIDER_TIMEOUT_SECONDS=45
AI_PROVIDER_TOTAL_TIMEOUT_SECONDS=75
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_secret_or_service_role_key
FINNHUB_API_KEY=your_finnhub_api_key
FMP_API_KEY=your_fmp_api_key
NEWSAPI_KEY=your_newsapi_key
```

After deployment, test:

```text
https://qfin-terminal.onrender.com/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "qfin-terminal-api",
  "ai_configured": true,
  "supabase_configured": true
}
```

## Security

Never expose these in frontend code or GitHub:

```text
AI_PROVIDER_API_KEY
SUPABASE_SERVICE_ROLE_KEY
.env
.env.local
```

The browser frontend should only call the Render backend URL. Supabase service-role access stays on the backend.

## License

MIT License.
