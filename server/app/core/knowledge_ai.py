"""Backend-only model selection for knowledge retrieval and extractive answers."""

from __future__ import annotations

import hashlib
import json

from app.core.ai_client import CompatibleModel, ModelEndpoint


def embedding_client(endpoint: ModelEndpoint | None = None) -> CompatibleModel:
    return CompatibleModel(endpoint or ModelEndpoint("", "", ""))


def embedding_configured(endpoint: ModelEndpoint | None = None) -> bool:
    return endpoint is not None and endpoint.configured


def embedding_version(endpoint: ModelEndpoint | None = None) -> str:
    if endpoint is None:
        return ""
    identity = json.dumps(
        [endpoint.base_url.rstrip("/"), endpoint.model, endpoint.version]
    )
    return hashlib.sha256(identity.encode()).hexdigest()[:24]


def chat_client(endpoint: ModelEndpoint | None = None) -> CompatibleModel:
    return CompatibleModel(endpoint or ModelEndpoint("", "", ""))
