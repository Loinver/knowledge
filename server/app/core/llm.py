"""OpenAI 兼容 LLM 客户端（第三批 AI 建议）。

只用环境配置的端点与密钥（KG_LLM_BASE_URL / KG_LLM_API_KEY / KG_LLM_MODEL），
不内置任何密钥或模拟回复：未配置时如实抛 KG.LLM_NOT_CONFIGURED。
仅要求 JSON 输出并做受信解析；建议永远只是建议——落库必须走人工确认。
"""

from __future__ import annotations

import json

import httpx

from app.core.config import get_settings
from app.core.error_codes import ErrorCode
from app.core.errors import KGError

_MAX_RESPONSE_CHARS = 200_000


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.llm_base_url and settings.llm_api_key and settings.llm_model)


def _require_configured() -> tuple[str, str, str, float]:
    settings = get_settings()
    if not (settings.llm_base_url and settings.llm_api_key and settings.llm_model):
        raise KGError(
            ErrorCode.LLM_NOT_CONFIGURED,
            {"reason": "llm_endpoints_not_configured"},
        )
    return (
        settings.llm_base_url.rstrip("/"),
        settings.llm_api_key,
        settings.llm_model,
        settings.llm_timeout_seconds,
    )


def _extract_json(content: str) -> list[dict]:
    """从回复中提取 JSON 数组；容忍 ```json 围栏。解析失败如实报错。"""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        raise KGError(ErrorCode.LLM_RESPONSE_INVALID, {"reason": "no_json_array"})
    try:
        parsed = json.loads(text[start : end + 1])
    except ValueError as exc:
        raise KGError(
            ErrorCode.LLM_RESPONSE_INVALID, {"reason": "invalid_json"}
        ) from exc
    if not isinstance(parsed, list) or not all(isinstance(i, dict) for i in parsed):
        raise KGError(
            ErrorCode.LLM_RESPONSE_INVALID, {"reason": "expected_object_list"}
        )
    return parsed[:50]


def chat_json(system: str, user: str) -> list[dict]:
    """调用 chat/completions 并解析 JSON 数组输出。"""
    base_url, api_key, model, timeout = _require_configured()
    url = f"{base_url}/chat/completions"
    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
            },
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise KGError(
            ErrorCode.LLM_UNAVAILABLE, {"reason": "llm_request_failed"}
        ) from exc
    if response.status_code >= 400:
        raise KGError(
            ErrorCode.LLM_UNAVAILABLE,
            {"reason": "llm_http_error", "status": response.status_code},
        )
    if len(response.text) > _MAX_RESPONSE_CHARS:
        raise KGError(ErrorCode.LLM_RESPONSE_INVALID, {"reason": "response_too_large"})
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError) as exc:
        raise KGError(
            ErrorCode.LLM_RESPONSE_INVALID, {"reason": "unexpected_response_shape"}
        ) from exc
    if not isinstance(content, str):
        raise KGError(ErrorCode.LLM_RESPONSE_INVALID, {"reason": "content_not_text"})
    return _extract_json(content)
