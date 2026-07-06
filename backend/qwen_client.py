import os
from typing import Any, Dict, List, Optional

import httpx


class QwenClientError(Exception):
    pass


def qwen_is_configured() -> bool:
    return bool(os.getenv("DASHSCOPE_API_KEY"))


def _timeout_seconds() -> float:
    try:
        return float(os.getenv("DASHSCOPE_TIMEOUT_SECONDS", "180"))
    except Exception:
        return 180.0


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
    timeout_seconds = _timeout_seconds()

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

    try:
        timeout = httpx.Timeout(timeout_seconds, connect=30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
    except httpx.TimeoutException as e:
        raise QwenClientError(
            f"Qwen request timed out after {timeout_seconds:.0f}s. "
            f"Model={model_name}. Base URL={base_url}. Error type={type(e).__name__}."
        ) from e
    except httpx.RequestError as e:
        raise QwenClientError(
            f"Qwen network request failed. Model={model_name}. Base URL={base_url}. "
            f"Error type={type(e).__name__}. Error={repr(e)}"
        ) from e

    if response.status_code >= 400:
        raise QwenClientError(
            f"Qwen API error {response.status_code}. Model={model_name}. Response={response.text[:1200]}"
        )

    try:
        return response.json()
    except Exception as e:
        raise QwenClientError(
            f"Qwen returned non-JSON response. Model={model_name}. Error={repr(e)}. Body={response.text[:1200]}"
        ) from e
