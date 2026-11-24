"""API contracts for administrator-managed AI model configurations."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from app.models.ai_model import AiModelCapability

AiModelSort = Literal[
    "name",
    "-name",
    "capability",
    "-capability",
    "created_at",
    "-created_at",
    "id",
    "-id",
]


def _trim(value: str | None) -> str | None:
    return value.strip() if value is not None else None


def _normalize_base_url(value: str | None) -> str | None:
    if value is None:
        return None
    raw = value.strip()
    if any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in raw
    ):
        raise ValueError("base_url must not contain whitespace or control characters")
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError as exc:
        raise ValueError("base_url must be a valid HTTP(S) URL") from exc
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("base_url must be a valid HTTP(S) URL")
    if any(character.isspace() for character in parts.hostname):
        raise ValueError("base_url must have a valid host")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("base_url must have a valid port")
    if parts.username is not None or parts.password is not None:
        raise ValueError("base_url must not contain credentials")
    if parts.query or parts.fragment:
        raise ValueError("base_url must not contain query or fragment")
    normalized = urlunsplit(
        (parts.scheme.lower(), parts.netloc, parts.path.rstrip("/"), "", "")
    )
    return normalized


class AiModelConfigCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    capability: AiModelCapability
    base_url: str = Field(min_length=1, max_length=2048)
    model: str = Field(min_length=1, max_length=255)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    model_version: str = Field(default="1", min_length=1, max_length=100)
    enabled: bool = False
    api_key: SecretStr | None = None

    _trim_name = field_validator("name", "model", "model_version", mode="after")(_trim)
    _normalize_url = field_validator("base_url", mode="after")(_normalize_base_url)


class AiModelConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: str | None = Field(default=None, min_length=1, max_length=2048)
    model: str | None = Field(default=None, min_length=1, max_length=255)
    timeout_seconds: int | None = Field(default=None, ge=1, le=120)
    model_version: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None
    api_key: SecretStr | None = None

    _trim_fields = field_validator("name", "model", "model_version", mode="after")(
        _trim
    )
    _normalize_url = field_validator("base_url", mode="after")(_normalize_base_url)

    @model_validator(mode="after")
    def reject_null_non_secret_fields(self) -> AiModelConfigUpdate:
        for field in self.model_fields_set - {"api_key"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class AiModelConfigOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    capability: AiModelCapability
    base_url: str
    model: str
    timeout_seconds: int
    model_version: str
    enabled: bool
    has_key: bool
    api_key_mask: Literal["***"] | None
    is_default: bool
    revision: int
    created_at: datetime
    updated_at: datetime


class AiModelConfigPage(BaseModel):
    items: list[AiModelConfigOut]
    total: int
    page: int
    page_size: int


class AiModelDefaultOut(BaseModel):
    capability: AiModelCapability
    config_id: int | None
    revision: int


class AiModelDefaultUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_id: int | None
