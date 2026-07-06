# QFin Terminal Clean Local Build

This is a fresh clean version. Do not mix it with the old broken folder.

## What works in this build

- Frontend opens at `http://localhost:5173`
- Buttons are clickable
- Generate Report calls FastAPI `/analyze`
- Ticker buttons update the prompt
- Backend opens at `http://127.0.0.1:8000`
- `/health`, `/docs`, `/analyze`, `/upload`, and `/` work
- Qwen is called only from backend if `DASHSCOPE_API_KEY` is added
- If Qwen key is missing, backend returns safe demo mode

## Setup

### Backend

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

### Backend .env

Create `backend/.env`:

```env
DASHSCOPE_API_KEY=your_qwen_dashscope_api_key
DASHSCOPE_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen-plus
SUPABASE_URL=https://gdwfsdmheymfhwberted.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_supabase_secret_or_service_role_key
```

For local testing, you can leave Supabase service role as placeholder. Qwen needs the real `DASHSCOPE_API_KEY`.

### Frontend

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

## Important

Do not put Qwen API key in frontend. Put it only in `backend/.env`.
