from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from qwen_client import QwenClientError, call_qwen, qwen_is_configured

app = FastAPI(title="QFin Terminal API", version="clean-local-1.2")

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
        return {
            "mode": payload.mode,
            "query": payload.query,
            "ticker": payload.ticker,
            "facts": metrics,
            "qwen_status": "not_configured",
            "ai_report": {
                "summary": "Demo mode only. Add DASHSCOPE_API_KEY in backend/.env or Render environment variables to enable Qwen.",
                "interpretation": "The backend is ready to send computed metrics to Qwen for grounded narration.",
                "watch_items": metrics["risk_flags"]
            },
            "answer": "Demo mode only. Add DASHSCOPE_API_KEY to enable Qwen. Backend is connected successfully.",
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
            "answer": content,
            "message": content,
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
            "answer": "Qwen call failed, but the Render backend is connected. Check your DASHSCOPE_API_KEY and model/base URL settings.",
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
