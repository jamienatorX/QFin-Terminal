"""Low-token compatibility probe for QFin's DashScope model candidates."""

import argparse
import asyncio
import base64
import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx

from main import normalize_finance_answer


SYSTEM_PROMPT = """You are QFin, a careful financial analysis assistant.
Use only the supplied facts. Do not invent data, sources, or tickers.
Return concise Markdown with exactly these sections in this order:
## Investment view
## Financial performance
## Valuation
## Key risks
## Verdict
Do not include methodology, caveat, disclaimer, or model commentary.
Use short paragraphs or bullets and explain what the numbers imply."""

USER_PROMPT = """Analyze this fictional company using only these verified facts:
Company: Northstar Retail (NRTS)
Revenue: USD 10.0B; revenue growth: 12%
Operating margin: 14%, versus 11% one year earlier
Free cash flow: USD 0.8B
Debt: USD 2.5B; cash: USD 1.2B
Forward P/E: 18x; peer median forward P/E: 21x
Main risks: consumer slowdown, inventory execution, refinancing costs
Give a balanced decision-useful assessment, not a buy or sell instruction."""

VISION_USER_PROMPT = """Analyze the uploaded financial screenshot using only information visibly present in it.
Keep the same five required QFin sections. Extract the company, ticker, price, and price change accurately.
State clearly when the image lacks enough fundamentals for a full investment conclusion. Do not guess."""

REQUIRED_HEADINGS = [
    "## Investment view",
    "## Financial performance",
    "## Valuation",
    "## Key risks",
    "## Verdict",
]
FORBIDDEN_OUTPUT = ["methodology", "model answer", "extra ticker-like", "direct answer"]


def score_answer(content: str) -> Dict[str, Any]:
    normalized = normalize_finance_answer(content, "company")
    heading_positions = [normalized.find(heading) for heading in REQUIRED_HEADINGS]
    headings_present = all(position >= 0 for position in heading_positions)
    headings_in_order = headings_present and heading_positions == sorted(heading_positions)
    forbidden = [term for term in FORBIDDEN_OUTPUT if term in normalized.lower()]
    return {
        "headings_present": headings_present,
        "headings_in_order": headings_in_order,
        "forbidden_terms": forbidden,
        "normalized_chars": len(normalized),
        "normalized_answer": normalized,
    }


def build_messages(image_path: str = "") -> List[Dict[str, Any]]:
    if not image_path:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ]
    path = Path(image_path)
    media_type = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": VISION_USER_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{encoded}"}},
            ],
        },
    ]


async def probe_model(
    client: httpx.AsyncClient,
    base_url: str,
    api_key: str,
    model: str,
    max_tokens: int,
    image_path: str = "",
) -> Dict[str, Any]:
    started = time.perf_counter()
    response = await client.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": build_messages(image_path),
            "temperature": 0.1,
            "max_tokens": max_tokens,
        },
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    if response.status_code >= 400:
        return {
            "model": model,
            "ok": False,
            "status_code": response.status_code,
            "latency_ms": elapsed_ms,
            "error": response.text[:500],
        }

    payload = response.json()
    content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = payload.get("usage") or {}
    return {
        "model": model,
        "ok": bool(content),
        "status_code": response.status_code,
        "latency_ms": elapsed_ms,
        "usage": usage,
        **score_answer(content),
    }


async def run(models: List[str], max_tokens: int, image_path: str = "") -> None:
    api_key = os.getenv("AI_PROVIDER_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise SystemExit("AI provider API key is not configured.")
    base_url = (
        os.getenv("AI_PROVIDER_BASE_URL")
        or os.getenv("DASHSCOPE_BASE_URL")
        or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    ).rstrip("/")
    timeout = httpx.Timeout(90.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for model in models:
            result = await probe_model(client, base_url, api_key, model, max_tokens, image_path)
            print(json.dumps(result, ensure_ascii=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", required=True, help="Comma-separated exact model codes")
    parser.add_argument("--max-tokens", type=int, default=700)
    parser.add_argument("--image", default="", help="Optional image path for a vision-model probe")
    args = parser.parse_args()
    if not 128 <= args.max_tokens <= 1200:
        raise SystemExit("Probe max tokens must be between 128 and 1200.")
    models = [model.strip() for model in args.models.split(",") if model.strip()]
    asyncio.run(run(models, args.max_tokens, args.image))


if __name__ == "__main__":
    main()
