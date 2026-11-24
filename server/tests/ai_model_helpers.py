"""Real encrypted model defaults and network-only doubles for isolated tests."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest
from app.core import llm
from app.core.ai_client import ModelEndpoint
from app.core.crypto import encrypt
from app.domain import ai_model_service
from app.models.ai_model import AiModelCapability, AiModelConfig, AiModelDefault
from sqlalchemy.orm import Session

FAKE_KEY = "runtime-test-key"


def seed_model(
    session: Session,
    *,
    capability: AiModelCapability = AiModelCapability.EMBEDDING,
    name: str = "Embedding",
    model: str = "fake",
    version: str = "test-v1",
    base_url: str = "https://model.example.test/v1",
    key: str = FAKE_KEY,
    select_default: bool = True,
) -> AiModelConfig:
    item = AiModelConfig(
        name=name,
        capability=capability,
        base_url=base_url,
        model=model,
        model_version=version,
        timeout_seconds=2,
        credential_cipher=encrypt(key),
        enabled=True,
        revision=1,
    )
    session.add(item)
    session.flush()
    if select_default:
        select_model(session, item)
    return item


def select_model(session: Session, item: AiModelConfig) -> None:
    default = session.get(AiModelDefault, item.capability)
    ai_model_service.set_default(
        session, item.capability, item.id, default.revision if default else 1
    )


def mock_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response]
    | Callable[[httpx.Request], Coroutine[None, None, httpx.Response]],
) -> None:
    original = httpx.AsyncClient

    def isolated(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return original(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", isolated)


def stub_chat_json(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    reply: Callable[[str, str], list[dict[str, Any]]],
) -> None:
    seed_model(
        session,
        capability=AiModelCapability.CHAT,
        name="Chat",
        model="database-suggestion-chat",
    )
    selected = ai_model_service.resolve_default(session, AiModelCapability.CHAT)
    assert selected is not None

    def respond(
        system: str, user: str, *, endpoint: ModelEndpoint | None = None
    ) -> list[dict[str, Any]]:
        assert endpoint is not None and endpoint == selected.endpoint
        return reply(system, user)

    monkeypatch.setattr(llm, "chat_json", respond)


def embedding_response(vectors: list[list[float]]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": [
                {"index": index, "embedding": vector}
                for index, vector in enumerate(vectors)
            ]
        },
    )
