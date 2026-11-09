"""Backend-only model selection for knowledge retrieval and extractive answers."""

from __future__ import annotations

import hashlib
import json

from app.core.ai_client import CompatibleModel, ModelEndpoint
from app.core.config import get_settings


def embedding_client() -> CompatibleModel:
    settings = get_settings()
    return CompatibleModel(
        ModelEndpoint(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
            version=settings.embedding_version,
            timeout_seconds=settings.embedding_timeout_seconds,
        )
    )


def embedding_configured() -> bool:
    return embedding_client().endpoint.configured


def embedding_version() -> str:
    endpoint = embedding_client().endpoint
    identity = json.dumps(
        [endpoint.base_url.rstrip("/"), endpoint.model, endpoint.version]
    )
    return hashlib.sha256(identity.encode()).hexdigest()[:24]


def chat_client() -> CompatibleModel:
    settings = get_settings()
    return CompatibleModel(
        ModelEndpoint(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    )
