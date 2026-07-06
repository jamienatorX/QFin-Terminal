# QFin Terminal

QFin Terminal is a Qwen-powered financial analyst dashboard for the Global AI Hackathon Series with Qwen Cloud.

The app has three main layers:

```text
Frontend: React / Vite dashboard
Backend: FastAPI service
AI: Qwen Cloud / DashScope API
Database: Supabase Postgres
```

## Current repository structure

The uploaded project is currently nested inside this path:

```text
qfin-terminal/qfin-terminal
```

Important folders:

```text
qfin-terminal/qfin-terminal/backend
qfin-terminal/qfin-terminal/frontend
qfin-terminal/qfin-terminal/supabase
```

## What works

- Frontend opens locally at `http://localhost:5173`
- Buttons are clickable
- Generate Report calls FastAPI `/analyze`
- Ticker buttons update the prompt
- Backend opens locally at `http://127.0.0.1:8000`
- `/`, `/health`, `/docs`, `/analyze`, and `/upload` work
- Qwen is called only from the backend if `DASHSCOPE_API_KEY` is configured
- If Qwen key is missing, backend returns safe demo mode

## Local backend setup

```powershell
cd qfin-terminal/qfin-terminal/backend
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
qfin-terminal/qfin-terminal/backend/.env
```

Add:

```env
DASHSCOPE_API_KEY=your_qwen_dashscope_api_key
DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen3.7-plus
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_secret_or_service_role_key
```

Do not commit `.env` to GitHub.

## Local frontend setup

```powershell
cd qfin-terminal/qfin-terminal/frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

To connect the frontend to a deployed backend, create:

```text
qfin-terminal/qfin-terminal/frontend/.env.local
```

Add:

```env
VITE_API_BASE_URL=https://your-backend-url.onrender.com
```

Restart the frontend after changing `.env.local`.

## Render backend deployment

This repo includes `render.yaml`.

For manual Render setup, use:

```text
Root Directory: qfin-terminal/qfin-terminal/backend
Build Command: pip install -r requirements.txt
Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
```

Set these environment variables in Render:

```env
DASHSCOPE_API_KEY=your_qwen_dashscope_api_key
DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen3.7-plus
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_secret_or_service_role_key
```

After deployment, test:

```text
https://your-render-backend-url.onrender.com/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "qfin-terminal-api",
  "qwen_configured": true
}
```

## Alibaba Cloud final deployment

Render is temporary. For final hackathon submission, deploy the backend to Alibaba Cloud ECS or Simple Application Server, then change the frontend variable:

```env
VITE_API_BASE_URL=https://your-alibaba-backend-url.com
```

## Security

Never expose these in frontend code or GitHub:

```text
DASHSCOPE_API_KEY
SUPABASE_SERVICE_ROLE_KEY
.env
.env.local
```

## License

MIT License.
