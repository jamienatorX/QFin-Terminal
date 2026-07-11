import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx


logger = logging.getLogger("qfin.qwen")


class QwenClientError(Exception):
    pass


def qwen_is_configured() -> bool:
    return bool(os.getenv("DASHSCOPE_API_KEY"))


def _timeout_seconds(task_type: str = "fast") -> float:
    defaults = {"general": 12.0, "fast": 10.0, "news": 15.0, "vision": 30.0, "deep": 40.0}
    task_env = os.getenv(f"DASHSCOPE_TIMEOUT_SECONDS_{task_type.upper()}")
    try:
        configured = float(task_env or os.getenv("DASHSCOPE_TIMEOUT_SECONDS", "45"))
        return max(5.0, min(configured, defaults.get(task_type, 20.0)))
    except Exception:
        return defaults.get(task_type, 20.0)


def _total_timeout_seconds(task_type: str = "fast") -> float:
    defaults = {"general": 18.0, "fast": 15.0, "news": 25.0, "vision": 50.0, "deep": 65.0}
    task_env = os.getenv(f"DASHSCOPE_TOTAL_TIMEOUT_SECONDS_{task_type.upper()}")
    try:
        configured = float(task_env or os.getenv("DASHSCOPE_TOTAL_TIMEOUT_SECONDS", "75"))
        return max(10.0, min(configured, defaults.get(task_type, 35.0)))
    except Exception:
        return defaults.get(task_type, 35.0)


def _max_tokens(task_type: str) -> int:
    defaults = {"deep": 2200, "vision": 1600, "news": 1200, "fast": 1000, "general": 700}
    env_name = f"DASHSCOPE_MAX_TOKENS_{task_type.upper()}"
    try:
        return max(256, int(os.getenv(env_name, str(defaults.get(task_type, 1000)))))
    except Exception:
        return defaults.get(task_type, 1000)


def _model_profile() -> Dict[str, str]:
    """
    QFin model routing profile.

    Keep Qwen3.7-Max for deep analyst work, but avoid using it for every
    request so quick summaries stay faster and cheaper.
    """
    fast_model = os.getenv("DASHSCOPE_MODEL_FAST") or os.getenv("DASHSCOPE_MODEL") or "qwen3.7-plus"
    return {
        "deep": os.getenv("DASHSCOPE_MODEL_DEEP") or "qwen3.7-max",
        "fast": fast_model,
        "flash": os.getenv("DASHSCOPE_MODEL_FLASH") or "qwen3.6-flash",
        "vision": os.getenv("DASHSCOPE_MODEL_VISION") or fast_model,
        "news": os.getenv("DASHSCOPE_NEWS_MODEL") or fast_model,
    }


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("type"), str):
                    parts.append(item["type"])
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _message_text(messages: List[Dict[str, Any]]) -> str:
    return "\n".join(_content_to_text(message.get("content", "")) for message in messages)


def _detect_task_type(messages: List[Dict[str, Any]]) -> str:
    text = _message_text(messages).lower()

    vision_signals = [
        "image_url",
        "input_image",
        "screenshot",
        "uploaded image",
        "analyze image",
        "analyse image",
        "chart image",
        "video analysis",
        "analyze video",
        "analyse video",
    ]
    if any(signal in text for signal in vision_signals):
        return "vision"

    # Route metadata is authoritative. Backend facts can contain phrases such
    # as "financial report" that must not promote a standard request to deep.
    if "analysis depth: standard" in text:
        return "fast"
    if "analysis depth: deep" in text:
        return "deep"

    deep_signals = [
        "full analysis",
        "deep dive",
        "comprehensive",
        "complete breakdown",
        "in-depth",
        "in depth",
        "analyst-grade",
        "financial report",
    ]
    if any(signal in text for signal in deep_signals):
        return "deep"

    news_signals = [
        "internal route: market news summary",
        "summarize the five news items",
        "headline",
        "market sentiment",
    ]
    if any(signal in text for signal in news_signals):
        return "news"

    if "internal route: general question" in text:
        return "general"

    finance_signals = [
        "internal route: exact ticker comparison",
        "internal route: single company analysis",
        "internal route: finance concept",
    ]
    if any(signal in text for signal in finance_signals):
        return "fast"

    if "public api facts" in text:
        return "general"

    public_or_summary_signals = [
        "quick summary",
        "summarize",
        "summarise",
        "summary",
        "internal route: finance concept",
    ]
    if any(signal in text for signal in public_or_summary_signals):
        return "fast"

    return "general"


def _dedupe_models(models: List[str]) -> List[str]:
    clean: List[str] = []
    for model in models:
        if model and model not in clean:
            clean.append(model)
    return clean


def _model_chain(task_type: str, explicit_model: Optional[str] = None) -> List[str]:
    if explicit_model:
        return [explicit_model]

    profile = _model_profile()
    if task_type == "deep":
        return _dedupe_models([profile["deep"], profile["fast"], profile["flash"]])
    if task_type == "vision":
        return _dedupe_models([profile["vision"], profile["fast"], profile["flash"]])
    if task_type == "news":
        return _dedupe_models([profile["news"], profile["fast"], profile["flash"]])
    if task_type == "general":
        return _dedupe_models([profile["flash"], profile["fast"]])
    return _dedupe_models([profile["fast"], profile["flash"]])


async def call_qwen(
    messages: List[Dict[str, Any]],
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

    task_type = _detect_task_type(messages)
    candidate_models = _model_chain(task_type, model)
    attempt_timeout_seconds = _timeout_seconds(task_type)
    total_timeout_seconds = _total_timeout_seconds(task_type)
    deadline = time.monotonic() + total_timeout_seconds

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error: Optional[QwenClientError] = None

    for model_name in candidate_models:
        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": _max_tokens(task_type),
        }

        if response_format:
            payload["response_format"] = response_format

        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 1.0:
            break
        timeout_seconds = min(attempt_timeout_seconds, remaining_seconds)

        try:
            timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds))
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException as e:
            last_error = QwenClientError(
                f"Qwen request timed out after {timeout_seconds:.0f}s. "
                f"Model={model_name}. Task={task_type}. Base URL={base_url}. "
                f"Error type={type(e).__name__}."
            )
            logger.warning("Qwen timeout on model %s; trying fallback if available.", model_name)
            continue
        except httpx.RequestError as e:
            last_error = QwenClientError(
                f"Qwen network request failed. Model={model_name}. Task={task_type}. Base URL={base_url}. "
                f"Error type={type(e).__name__}. Error={repr(e)}"
            )
            logger.warning("Qwen network error on model %s; trying fallback if available.", model_name)
            continue

        if response.status_code >= 400:
            error = QwenClientError(
                f"Qwen API error {response.status_code}. Model={model_name}. Task={task_type}. "
                f"Response={response.text[:1200]}"
            )
            if response.status_code in {401, 403}:
                raise error
            last_error = error
            logger.warning("Qwen API error on model %s; trying fallback if available.", model_name)
            continue

        try:
            data = response.json()
            data["_qfin_model_used"] = model_name
            data["_qfin_task_type"] = task_type
            return data
        except Exception as e:
            last_error = QwenClientError(
                f"Qwen returned non-JSON response. Model={model_name}. Task={task_type}. "
                f"Error={repr(e)}. Body={response.text[:1200]}"
            )
            logger.warning("Qwen returned non-JSON on model %s; trying fallback if available.", model_name)
            continue

    if last_error:
        raise last_error

    raise QwenClientError(
        f"Qwen could not complete the request within the {total_timeout_seconds:.0f}s total response budget."
    )

