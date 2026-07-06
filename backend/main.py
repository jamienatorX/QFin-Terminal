from dotenv import load_dotenv
load_dotenv()

import re
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from qwen_client import QwenClientError, call_qwen, qwen_is_configured

app = FastAPI(title="QFin Terminal API", version="clean-local-1.3")

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

class ChatMessage(BaseModel):
    role: Optional[str] = "user"
    content: str

class ChatRequest(BaseModel):
    message: Optional[str] = None
    query: Optional[str] = None
    prompt: Optional[str] = None
    ticker: Optional[str] = None
    mode: Optional[str] = "chat"
    messages: Optional[List[ChatMessage]] = None

def extract_chat_query(payload: ChatRequest) -> str:
    if payload.message:
        return payload.message
    if payload.query:
        return payload.query
    if payload.prompt:
        return payload.prompt
    if payload.messages:
        user_messages = [m.content for m in payload.messages if (m.role or "user") == "user"]
        if user_messages:
            return user_messages[-1]
        return payload.messages[-1].content
    return "Analyze the selected company and explain key financial risks."

def clean_frontend_text(text: str) -> str:
    cleaned = text.replace("**", "").replace("*", "").replace("#", "")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n[ \t]+", "\n", cleaned)
    cleaned = cleaned.strip()
    cleaned = re.sub(r"(?<!\n)(Fact\.)", r"\n\n\1", cleaned)
    cleaned = re.sub(r"(?<!\n)(Interpretation\.)", r"\n\n\1", cleaned)
    cleaned = re.sub(r"(?<!\n)(Watch Items\.)", r"\n\n\1", cleaned)
    cleaned = re.sub(r"(?<!\n)(Disclaimer\.)", r"\n\n\1", cleaned)
    return cleaned.strip()

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
        "Do not give buy, sell, or hold recommendations. "
        "Write in plain text only. Do not use Markdown, asterisks, bullets, hashtags, tables, or JSON. "
        "Use clear section labels exactly as: Fact. Interpretation. Watch Items. Disclaimer. "
        "Keep the answer readable even if line breaks are removed by the frontend."
    )

    user_message = f'''
User request: {payload.query}
Ticker: {payload.ticker or "Not provided"}
Mode: {payload.mode}

Backend-computed metrics:
{metrics}

Write a concise financial analysis report using only the data above.
Use this plain text format:
Fact. Revenue Growth: ... Gross Margin: ... Debt-to-Equity Ratio: ...

Interpretation. ...

Watch Items. 1. Revenue Quality: ... 2. Margin Sustainability: ... 3. Relative Leverage: ...

Disclaimer. ...
'''

    return [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
    ]

@app.get("/")
def root(request: Request):
    base_url = str(request.base_url).rstrip("/")
    return {
        "app": "QFin Terminal API",
        "status": "running",
        "docs": f"{base_url}/docs",
        "health": f"{base_url}/health",
        "chat": f"{base_url}/chat",
        "chat_stream": f"{base_url}/chat/stream"
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
        fallback = "Fact. Demo mode is active because DASHSCOPE_API_KEY is not configured. Interpretation. The backend is connected successfully, but Qwen is not enabled yet. Watch Items. 1. Add DASHSCOPE_API_KEY in Render environment variables. 2. Confirm DASHSCOPE_MODEL is set correctly. Disclaimer. This is for educational and analytical use only, not financial advice."
        return {
            "mode": payload.mode,
            "query": payload.query,
            "ticker": payload.ticker,
            "facts": metrics,
            "qwen_status": "not_configured",
            "ai_report": {
                "summary": fallback,
                "interpretation": "The backend is ready to send computed metrics to Qwen for grounded narration.",
                "watch_items": metrics["risk_flags"]
            },
            "answer": fallback,
            "disclaimer": "For educational and analytical use only. Not financial advice."
        }

    try:
        qwen_response = await call_qwen(messages)
        raw_content = qwen_response["choices"][0]["message"]["content"]
        content = clean_frontend_text(raw_content)
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
            "answer": content,
            "message": content,
            "disclaimer": "For educational and analytical use only. Not financial advice."
        }
    except (QwenClientError, KeyError, IndexError) as error:
        fallback = "Fact. The Render backend is connected, but the Qwen call failed. Interpretation. This usually means the DASHSCOPE_API_KEY, model name, or base URL needs to be checked. Watch Items. 1. Check DASHSCOPE_API_KEY in Render. 2. Check DASHSCOPE_BASE_URL. 3. Check DASHSCOPE_MODEL. Disclaimer. This is for educational and analytical use only, not financial advice."
        return {
            "mode": payload.mode,
            "query": payload.query,
            "ticker": payload.ticker,
            "facts": metrics,
            "qwen_status": "error",
            "error": str(error),
            "ai_report": {
                "summary": fallback,
                "watch_items": metrics["risk_flags"]
            },
            "answer": fallback,
            "disclaimer": "For educational and analytical use only. Not financial advice."
        }

@app.post("/chat")
async def chat(payload: ChatRequest):
    query = extract_chat_query(payload)
    result = await analyze(
        AnalyzeRequest(
            query=query,
            ticker=payload.ticker,
            mode=payload.mode or "chat"
        )
    )
    return {
        "id": "qfin-chat-response",
        "role": "assistant",
        "content": result.get("answer") or result.get("ai_report", {}).get("content") or result.get("ai_report", {}).get("summary"),
        "answer": result.get("answer"),
        "data": result
    }

@app.post("/chat/stream")
async def chat_stream(payload: ChatRequest):
    async def text_generator():
        result = await chat(payload)
        content = result.get("content") or "No response generated."
        yield content

    return StreamingResponse(text_generator(), media_type="text/plain; charset=utf-8")

@app.post("/chat/upload")
async def chat_upload(file: UploadFile = File(...)):
    return await upload_statement(file)

@app.get("/ticker/resolve")
def resolve_ticker(symbol: Optional[str] = None, query: Optional[str] = None):
    raw = symbol or query or "BABA"
    normalized = raw.strip().upper()
    return {
        "symbol": normalized,
        "ticker": normalized,
        "name": normalized,
        "status": "resolved"
    }

@app.post("/upload")
async def upload_statement(file: UploadFile = File(...)):
    return {
        "filename": file.filename,
        "status": "received",
        "next_step": "Parse CSV or Excel, normalize financial statement rows, then call /analyze."
    }
