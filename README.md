# QFin Terminal

QFin Terminal is a Qwen-powered financial analyst dashboard for the Global AI Hackathon Series with Qwen Cloud.

The app has four main layers:

```text
Frontend: React / Vite website deployed on Vercel
Backend: FastAPI service deployed on Render
AI: Qwen Cloud / DashScope API with intelligent model routing
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
- Qwen and Supabase are called only from the backend

## Qwen model routing

QFin does not use the strongest model for every request. The backend routes requests by task so the app stays faster and cheaper:

```text
Deep financial report / analyst agent  -> Qwen3.7-Max
Quick summary / cheaper backup         -> Qwen3.7-Plus or Qwen3.6-Flash
Analyze image/chart/video directly     -> Qwen3.7-Plus
```

If Qwen3.7-Max times out or returns a temporary API error, the backend automatically tries the faster backup models. Authentication errors still stop immediately because they mean the API key or base URL is wrong.

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
DASHSCOPE_API_KEY=your_qwen_dashscope_api_key
DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL_DEEP=qwen3.7-max
DASHSCOPE_MODEL_FAST=qwen3.7-plus
DASHSCOPE_MODEL_FLASH=qwen3.6-flash
DASHSCOPE_MODEL_VISION=qwen3.7-plus
DASHSCOPE_NEWS_MODEL=qwen3.7-plus
DASHSCOPE_TIMEOUT_SECONDS=120
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
DASHSCOPE_API_KEY=your_qwen_dashscope_api_key
DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL_DEEP=qwen3.7-max
DASHSCOPE_MODEL_FAST=qwen3.7-plus
DASHSCOPE_MODEL_FLASH=qwen3.6-flash
DASHSCOPE_MODEL_VISION=qwen3.7-plus
DASHSCOPE_NEWS_MODEL=qwen3.7-plus
DASHSCOPE_TIMEOUT_SECONDS=120
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
  "qwen_configured": true,
  "supabase_configured": true
}
```

## Security

Never expose these in frontend code or GitHub:

```text
DASHSCOPE_API_KEY
SUPABASE_SERVICE_ROLE_KEY
.env
.env.local
```

The browser frontend should only call the Render backend URL. Supabase service-role access stays on the backend.

## License

MIT License.
