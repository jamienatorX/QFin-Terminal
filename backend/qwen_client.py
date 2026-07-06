import os
from typing import Any, Dict, List, Optional

import httpx


class QwenClientError(Exception):
    pass


def qwen_is_configured() -> bool:
    return bool(os.getenv("DASHSCOPE_API_KEY"))


async def call_qwen(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    response_format: Optional[Dict[str, str]] = None,
    temperature: float = 0.2,
) -> Dict[str, Any]:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise QwenClientError("DASHSCOPE_API_KEY is not configured.")

    base_url = os.getenv(
        "DASHSCOPE_BASE_URL",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    ).rstrip("/")

    model_name = model or os.getenv("DASHSCOPE_MODEL", "qwen-plus")

    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
    }

    if response_format:
        payload["response_format"] = response_format

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
        )

    if response.status_code >= 400:
        raise QwenClientError(f"Qwen API error {response.status_code}: {response.text}")

    return response.json()
