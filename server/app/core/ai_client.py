"""Bounded AI transport. Endpoints and secrets are supplied only by the backend.

Business callers use chat/embedding protocols. This adapter follows the existing
compatible JSON HTTP API; it never chooses a vendor or supplies a default key.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.core.vector_math import normalized_vector

logger = logging.getLogger(__name__)
MAX_RESPONSE_BYTES = 2_000_000
MAX_DIMENSIONS = 4096


@dataclass(frozen=True)
class ModelEndpoint:
    base_url: str
    api_key: str = field(repr=False)
    model: str
    version: str = "1"
    timeout_seconds: float = 30

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


class ChatModel(Protocol):
    async def chat(self, system: str, user: str) -> str: ...


class EmbeddingModel(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def invalid_response(reason: str) -> KGError:
    return KGError(ErrorCode.LLM_RESPONSE_INVALID, {"reason": reason})


class CompatibleModel:
    def __init__(self, endpoint: ModelEndpoint) -> None:
        self.endpoint = endpoint

    async def _request(self, operation: str, payload: dict[str, object]) -> dict:
        endpoint = self.endpoint
        if not endpoint.configured:
            raise KGError(ErrorCode.LLM_NOT_CONFIGURED, {"capability": operation})
        request_id = uuid.uuid4().hex
        started = time.monotonic()
        outcome = "SUCCESS"
        try:
            # One absolute budget includes both attempts, response reading, and
            # cancellation. Redirects must not forward the bearer credential.
            async with asyncio.timeout(endpoint.timeout_seconds):
                async with httpx.AsyncClient(
                    timeout=endpoint.timeout_seconds, follow_redirects=False
                ) as client:
                    for attempt in range(2):
                        try:
                            async with client.stream(
                                "POST",
                                f"{endpoint.base_url.rstrip('/')}/{operation}",
                                headers={
                                    "Authorization": f"Bearer {endpoint.api_key}",
                                    "Accept-Encoding": "identity",
                                },
                                json={"model": endpoint.model, **payload},
                            ) as response:
                                if response.status_code >= 300:
                                    reason = {
                                        401: "model_unauthorized",
                                        403: "model_unauthorized",
                                        429: "model_rate_or_quota_limit",
                                    }.get(response.status_code, "model_unavailable")
                                    raise KGError(
                                        ErrorCode.LLM_UNAVAILABLE,
                                        {
                                            "reason": reason,
                                            "status": response.status_code,
                                        },
                                    )
                                if (
                                    response.headers.get(
                                        "content-encoding", "identity"
                                    ).lower()
                                    != "identity"
                                ):
                                    raise invalid_response(
                                        "compressed_response_not_supported"
                                    )
                                content = bytearray()
                                async for part in response.aiter_bytes():
                                    if len(part) > MAX_RESPONSE_BYTES - len(content):
                                        raise invalid_response("response_too_large")
                                    content.extend(part)
                                try:
                                    result = json.loads(content)
                                except (
                                    ValueError,
                                    UnicodeError,
                                    RecursionError,
                                ) as exc:
                                    raise invalid_response("invalid_json") from exc
                                if not isinstance(result, dict):
                                    raise invalid_response("unexpected_response_shape")
                                return result
                        except (httpx.ConnectError, httpx.ConnectTimeout):
                            # Retry only connection establishment: no response or
                            # partially sent inference is replayed.
                            if attempt:
                                raise
                    raise AssertionError("unreachable")
        except (TimeoutError, httpx.TimeoutException) as exc:
            outcome = "TIMEOUT"
            raise KGError(
                ErrorCode.LLM_UNAVAILABLE, {"reason": "model_timeout"}
            ) from exc
        except httpx.HTTPError as exc:
            outcome = "FAILED"
            raise KGError(
                ErrorCode.LLM_UNAVAILABLE, {"reason": "model_unavailable"}
            ) from exc
        except asyncio.CancelledError:
            outcome = "CANCELLED"
            raise
        except KGError:
            outcome = "FAILED"
            raise
        finally:
            # Never log URL, headers, prompts, response text or exception bodies.
            logger.info(
                "ai_request operation=%s model=%s request_id=%s "
                "elapsed_ms=%d outcome=%s",
                operation,
                endpoint.model,
                request_id,
                int((time.monotonic() - started) * 1000),
                outcome,
            )

    async def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0,
        max_tokens: int | None = 1500,
    ) -> str:
        payload: dict[str, object] = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        result = await self._request("chat/completions", payload)
        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise invalid_response("unexpected_response_shape") from exc
        if not isinstance(content, str) or not content.strip():
            raise invalid_response("content_not_text")
        return content

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not 1 <= len(texts) <= 32 or any(not text.strip() for text in texts):
            raise KGError(
                ErrorCode.INVALID_REQUEST, {"reason": "invalid_embedding_input"}
            )
        result = await self._request(
            "embeddings", {"input": texts, "encoding_format": "float"}
        )
        data = result.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise invalid_response("embedding_count_mismatch")
        vectors: dict[int, list[float]] = {}
        for item in data:
            if not isinstance(item, dict):
                raise invalid_response("invalid_embedding")
            index, values = item.get("index"), item.get("embedding")
            if (
                type(index) is not int
                or index not in range(len(texts))
                or index in vectors
                or not isinstance(values, list)
                or not 1 <= len(values) <= MAX_DIMENSIONS
                or any(type(value) not in (int, float) for value in values)
            ):
                raise invalid_response("invalid_embedding")
            try:
                vector = normalized_vector([float(value) for value in values])
            except (OverflowError, ValueError) as exc:
                raise invalid_response("invalid_embedding") from exc
            vectors[index] = vector
        if len({len(vector) for vector in vectors.values()}) != 1:
            raise invalid_response("embedding_dimension_mismatch")
        return [vectors[index] for index in range(len(texts))]
