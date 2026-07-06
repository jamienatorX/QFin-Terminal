from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, Optional

from qwen_client import QwenClientError, call_qwen, qwen_is_configured

app = FastAPI(title="QFin Terminal API", version="clean-local-1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalyzeRequest(BaseModel):
    query: str
    ticker: Optional[str] = None
    mode: str = "full_report"

def calculate_demo_metrics() -> Dict[str, Any]:
    return {
        "revenue_growth": 0.184,
        "gross_margin": 0.421,
        "debt_to_equity": 0.68,
        "risk_flags": [
            "Revenue quality should be checked against cash flow.",
            "Margin expansion may depend on one-off cost reductions.",
            "Leverage is moderate but should be compared with peers."
        ]
    }

def build_grounded_prompt(payload: AnalyzeRequest, metrics: Dict[str, Any]):
    system_message = (
        "You are QFin Terminal, a careful financial analyst assistant. "
        "You must not invent financial numbers. Use only the structured metrics provided by the backend. "
        "Separate your answer into Fact, Interpretation, Watch Items, and Disclaimer. "
        "Do not give buy, sell, or hold recommendations."
    )

    user_message = f'''
User request: {payload.query}
Ticker: {payload.ticker or "Not provided"}
Mode: {payload.mode}

Backend-computed metrics:
{metrics}

Write a concise financial analysis report using only the data above.
'''

    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
    ]

@app.get("/")
def root():
    return {
        "app": "QFin Terminal API",
        "status": "running",
        "docs": "http://127.0.0.1:8000/docs",
        "health": "http://127.0.0.1:8000/health"
    }

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "qfin-terminal-api",
        "qwen_configured": qwen_is_configured()
    }

@app.post("/analyze")
async def analyze(payload: AnalyzeRequest):
    metrics = calculate_demo_metrics()
    messages = build_grounded_prompt(payload, metrics)

    if not qwen_is_configured():
        return {
            "mode": payload.mode,
            "query": payload.query,
            "ticker": payload.ticker,
            "facts": metrics,
            "qwen_status": "not_configured",
            "ai_report": {
                "summary": "Demo mode only. Add DASHSCOPE_API_KEY in backend/.env to enable Qwen.",
                "interpretation": "The backend is ready to send computed metrics to Qwen for grounded narration.",
                "watch_items": metrics["risk_flags"]
            },
            "disclaimer": "For educational and analytical use only. Not financial advice."
        }

    try:
        qwen_response = await call_qwen(messages)
        content = qwen_response["choices"][0]["message"]["content"]
        return {
            "mode": payload.mode,
            "query": payload.query,
            "ticker": payload.ticker,
            "facts": metrics,
            "qwen_status": "success",
            "ai_report": {
                "content": content,
                "raw_model": qwen_response.get("model"),
                "usage": qwen_response.get("usage")
            },
            "disclaimer": "For educational and analytical use only. Not financial advice."
        }
    except (QwenClientError, KeyError, IndexError) as error:
        return {
            "mode": payload.mode,
            "query": payload.query,
            "ticker": payload.ticker,
            "facts": metrics,
            "qwen_status": "error",
            "error": str(error),
            "ai_report": {
                "summary": "Qwen call failed, so the backend returned a safe fallback response.",
                "watch_items": metrics["risk_flags"]
            },
            "disclaimer": "For educational and analytical use only. Not financial advice."
        }

@app.post("/upload")
async def upload_statement(file: UploadFile = File(...)):
    return {
        "filename": file.filename,
        "status": "received",
        "next_step": "Parse CSV or Excel, normalize financial statement rows, then call /analyze."
    }
