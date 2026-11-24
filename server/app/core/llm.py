"""OpenAI 兼容 LLM 客户端（第三批 AI 建议）。

调用方从数据库默认配置解析端点与密钥，按操作传入不可变端点快照，
不内置任何密钥或模拟回复：未配置时如实抛 KG.LLM_NOT_CONFIGURED。
仅要求 JSON 输出并做受信解析；建议永远只是建议——落库必须走人工确认。
"""

from __future__ import annotations

import asyncio
import json

from app.core.ai_client import CompatibleModel, ModelEndpoint
from app.core.error_codes import ErrorCode
from app.core.errors import KGError


def is_configured(endpoint: ModelEndpoint | None = None) -> bool:
    return endpoint is not None and endpoint.configured


def _require_configured(endpoint: ModelEndpoint | None) -> ModelEndpoint:
    if endpoint is None or not endpoint.configured:
        raise KGError(
            ErrorCode.LLM_NOT_CONFIGURED,
            {"reason": "default_chat_model_not_configured"},
        )
    return endpoint


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
    except (ValueError, RecursionError) as exc:
        raise KGError(
            ErrorCode.LLM_RESPONSE_INVALID, {"reason": "invalid_json"}
        ) from exc
    if not isinstance(parsed, list) or not all(isinstance(i, dict) for i in parsed):
        raise KGError(
            ErrorCode.LLM_RESPONSE_INVALID, {"reason": "expected_object_list"}
        )
    return parsed[:50]


def chat_json(
    system: str, user: str, *, endpoint: ModelEndpoint | None = None
) -> list[dict]:
    """调用 chat/completions 并解析 JSON 数组输出。"""
    selected = _require_configured(endpoint)
    # Existing synchronous suggestion endpoints keep their public JSON-array
    # contract and share the same bounded, secret-safe transport as knowledge QA.
    client = CompatibleModel(selected)
    content = asyncio.run(client.chat(system, user, temperature=0.2, max_tokens=None))
    if len(content) > 200_000:
        raise KGError(ErrorCode.LLM_RESPONSE_INVALID, {"reason": "response_too_large"})
    return _extract_json(content)
