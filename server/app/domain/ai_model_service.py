"""Administrator-managed AI model configuration rules.

This module owns validation and revision handling. HTTP routes own the
transaction boundary; no function here commits or calls a model endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.ai_client import ModelEndpoint
from app.core.crypto import decrypt, encrypt
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.ai_model import AiModelCapability, AiModelConfig, AiModelDefault
from app.schemas.ai_model import AiModelConfigCreate, AiModelConfigUpdate, AiModelSort

_DEFAULT_CAPABILITIES: Final[tuple[AiModelCapability, ...]] = (
    AiModelCapability.CHAT,
    AiModelCapability.EMBEDDING,
)
CapabilityValue = AiModelCapability | str


@dataclass(frozen=True)
class ResolvedModel:
    config_id: int
    config_revision: int
    default_revision: int
    capability: AiModelCapability
    model_version: str
    endpoint: ModelEndpoint


def ensure_default_rows(session: Session) -> None:
    """Add missing development default rows without resetting selections."""
    existing = set(session.scalars(select(AiModelDefault.capability)).all())
    for capability in _DEFAULT_CAPABILITIES:
        if capability not in existing:
            session.add(
                AiModelDefault(capability=capability, config_id=None, revision=1)
            )
    session.flush()


def _invalid(reason: str, field: str | None = None) -> KGError:
    params: dict[str, object] = {"reason": reason}
    if field is not None:
        params["field"] = field
    return KGError(ErrorCode.INVALID_REQUEST, params)


def _capability(value: CapabilityValue) -> AiModelCapability:
    return AiModelCapability(value)


def parse_if_match(value: str | None) -> int:
    if value is None:
        raise _invalid("if_match_required")
    candidate = value.strip()
    if candidate.startswith("W/"):
        candidate = candidate[2:].strip()
    if len(candidate) >= 2 and candidate[0] == '"' and candidate[-1] == '"':
        candidate = candidate[1:-1]
    try:
        revision = int(candidate)
    except ValueError as exc:
        raise _invalid("if_match_invalid") from exc
    if revision < 1:
        raise _invalid("if_match_invalid")
    return revision


def _secret_value(payload: AiModelConfigCreate | AiModelConfigUpdate) -> str | None:
    if payload.api_key is None:
        return None
    value = payload.api_key.get_secret_value()
    if not value.strip() or value.strip() == "***":
        raise _invalid("api_key_invalid", "api_key")
    return value


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    return parts.scheme.lower(), (parts.hostname or "").lower(), parts.port


def _default_row(session: Session, capability: AiModelCapability) -> AiModelDefault:
    row = session.scalar(
        select(AiModelDefault)
        .where(AiModelDefault.capability == capability)
        .with_for_update()
    )
    if row is None:
        row = AiModelDefault(capability=capability, config_id=None, revision=1)
        session.add(row)
        session.flush()
    return row


def _config(session: Session, config_id: int, *, lock: bool = False) -> AiModelConfig:
    statement = select(AiModelConfig).where(AiModelConfig.id == config_id)
    if lock:
        statement = statement.with_for_update()
    item = session.scalar(statement)
    if item is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"resource": "ai_model_config"})
    return item


def _ensure_name_available(
    session: Session, name: str, *, exclude_id: int | None = None
) -> None:
    statement = select(AiModelConfig.id).where(AiModelConfig.name == name)
    if exclude_id is not None:
        statement = statement.where(AiModelConfig.id != exclude_id)
    if session.scalar(statement) is not None:
        raise KGError(
            ErrorCode.ALREADY_EXISTS, {"resource": "ai_model_config", "field": "name"}
        )


def _advance_default(
    session: Session, row: AiModelDefault, config_id: int | None
) -> AiModelDefault:
    updated = session.scalar(
        update(AiModelDefault)
        .where(
            AiModelDefault.capability == row.capability,
            AiModelDefault.revision == row.revision,
        )
        .values(config_id=config_id, revision=AiModelDefault.revision + 1)
        .returning(AiModelDefault)
        .execution_options(populate_existing=True)
    )
    if updated is None:
        session.refresh(row)
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {
                "resource": "ai_model_default",
                "expected": row.revision,
                "actual": row.revision - 1,
            },
        )
    return updated


def _claim_config_revision(
    session: Session, item: AiModelConfig, expected: int
) -> AiModelConfig:
    updated = session.scalar(
        update(AiModelConfig)
        .where(AiModelConfig.id == item.id, AiModelConfig.revision == expected)
        .values(revision=AiModelConfig.revision + 1)
        .returning(AiModelConfig)
        .execution_options(populate_existing=True)
    )
    if updated is None:
        session.refresh(item)
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {
                "resource": "ai_model_config",
                "expected": item.revision,
                "actual": expected,
            },
        )
    return updated


def create_config(session: Session, payload: AiModelConfigCreate) -> AiModelConfig:
    key = _secret_value(payload)
    if payload.enabled and key is None:
        raise _invalid("enabled_requires_key", "api_key")
    _ensure_name_available(session, payload.name)
    item = AiModelConfig(
        name=payload.name,
        capability=payload.capability,
        base_url=payload.base_url,
        model=payload.model,
        timeout_seconds=payload.timeout_seconds,
        model_version=payload.model_version,
        credential_cipher=encrypt(key) if key is not None else None,
        enabled=payload.enabled,
        revision=1,
    )
    session.add(item)
    session.flush()
    return item


def get_config(session: Session, config_id: int) -> AiModelConfig:
    return _config(session, config_id)


def list_defaults(session: Session) -> list[AiModelDefault]:
    return list(session.scalars(select(AiModelDefault)).all())


def update_config(
    session: Session,
    config_id: int,
    payload: AiModelConfigUpdate,
    if_match: int,
) -> AiModelConfig:
    capability = session.scalar(
        select(AiModelConfig.capability).where(AiModelConfig.id == config_id)
    )
    if capability is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"resource": "ai_model_config"})
    # All writers lock the selection row before the config row.
    default = _default_row(session, capability)
    item = _config(session, config_id, lock=True)
    if item.revision != if_match:
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {
                "resource": "ai_model_config",
                "expected": item.revision,
                "actual": if_match,
            },
        )
    fields = payload.model_fields_set
    explicit_key = "api_key" in fields
    new_key = _secret_value(payload) if explicit_key else None
    retained_key = decrypt(item.credential_cipher) if item.credential_cipher else None
    next_key = new_key if explicit_key else retained_key
    next_enabled = bool(payload.enabled) if "enabled" in fields else bool(item.enabled)

    if "name" in fields and payload.name is not None:
        _ensure_name_available(session, payload.name, exclude_id=config_id)
    if (
        "base_url" in fields
        and payload.base_url is not None
        and retained_key is not None
        and "api_key" not in fields
        and _origin(item.base_url) != _origin(payload.base_url)
    ):
        raise _invalid("api_key_required_for_origin_change", "api_key")
    if explicit_key and new_key is None:
        if "enabled" in fields and next_enabled:
            raise _invalid("enabled_requires_key", "enabled")
        next_enabled = False
    if next_enabled and next_key is None:
        raise _invalid("enabled_requires_key", "api_key")

    item = _claim_config_revision(session, item, if_match)
    if "name" in fields and payload.name is not None:
        item.name = payload.name
    if "base_url" in fields and payload.base_url is not None:
        item.base_url = payload.base_url
    for name in ("model", "timeout_seconds", "model_version"):
        if name in fields and getattr(payload, name) is not None:
            setattr(item, name, getattr(payload, name))
    if explicit_key:
        item.credential_cipher = encrypt(new_key) if new_key is not None else None
    item.enabled = next_enabled
    if (
        (explicit_key and new_key is None) or not item.enabled
    ) and default.config_id == item.id:
        _advance_default(session, default, None)
    session.flush()
    return item


def delete_config(session: Session, config_id: int, if_match: int) -> None:
    capability = session.scalar(
        select(AiModelConfig.capability).where(AiModelConfig.id == config_id)
    )
    if capability is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"resource": "ai_model_config"})
    default = _default_row(session, capability)
    item = _config(session, config_id, lock=True)
    if item.revision != if_match:
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {
                "resource": "ai_model_config",
                "expected": item.revision,
                "actual": if_match,
            },
        )
    _claim_config_revision(session, item, if_match)
    if default.config_id == item.id:
        _advance_default(session, default, None)
    session.delete(item)
    session.flush()


def list_configs(
    session: Session,
    *,
    q: str,
    capability: AiModelCapability | None,
    enabled: bool | None,
    page: int,
    page_size: int,
    sort: AiModelSort,
) -> tuple[list[AiModelConfig], int, set[int]]:
    statement = select(AiModelConfig)
    count_statement = select(func.count()).select_from(AiModelConfig)
    filters: list[ColumnElement[bool]] = []
    if q:
        filters.append(
            or_(
                AiModelConfig.name.ilike(f"%{q}%"),
                AiModelConfig.model.ilike(f"%{q}%"),
            )
        )
    if capability is not None:
        filters.append(AiModelConfig.capability == capability)
    if enabled is not None:
        filters.append(AiModelConfig.enabled == enabled)
    if filters:
        statement = statement.where(*filters)
        count_statement = count_statement.where(*filters)
    descending = sort.startswith("-")
    field_name = sort[1:] if descending else sort
    field = getattr(AiModelConfig, field_name)
    statement = statement.order_by(
        field.desc() if descending else field.asc(), AiModelConfig.id.asc()
    )
    items = list(
        session.scalars(statement.offset((page - 1) * page_size).limit(page_size))
    )
    default_ids = {
        row.config_id for row in list_defaults(session) if row.config_id is not None
    }
    total = session.scalar(count_statement) or 0
    return items, int(total), default_ids


def get_default_model(
    session: Session, capability: CapabilityValue
) -> AiModelConfig | None:
    capability = _capability(capability)
    row = session.scalar(
        select(AiModelDefault).where(AiModelDefault.capability == capability)
    )
    if row is None or row.config_id is None:
        return None
    item = session.get(AiModelConfig, row.config_id)
    if item is None or not item.enabled or not item.credential_cipher:
        return None
    return item


def resolve_default(
    session: Session, capability: CapabilityValue
) -> ResolvedModel | None:
    capability = _capability(capability)
    row = session.scalar(
        select(AiModelDefault).where(AiModelDefault.capability == capability)
    )
    if row is None or row.config_id is None:
        return None
    item = session.get(AiModelConfig, row.config_id)
    if item is None or not item.enabled or not item.credential_cipher:
        return None
    try:
        key = decrypt(item.credential_cipher)
    except ValueError as exc:
        raise KGError(
            ErrorCode.LLM_UNAVAILABLE, {"reason": "stored_credential_invalid"}
        ) from exc
    return ResolvedModel(
        config_id=item.id,
        config_revision=item.revision,
        default_revision=row.revision,
        capability=capability,
        model_version=item.model_version,
        endpoint=ModelEndpoint(
            base_url=item.base_url,
            api_key=key,
            model=item.model,
            version=item.model_version,
            timeout_seconds=float(item.timeout_seconds),
        ),
    )


def is_current(session: Session, resolved: ResolvedModel) -> bool:
    row = session.scalar(
        select(AiModelDefault)
        .where(AiModelDefault.capability == resolved.capability)
        .execution_options(populate_existing=True)
    )
    if (
        row is None
        or row.config_id != resolved.config_id
        or row.revision != resolved.default_revision
    ):
        return False
    item = session.get(AiModelConfig, resolved.config_id, populate_existing=True)
    return bool(
        item
        and item.revision == resolved.config_revision
        and item.enabled
        and item.credential_cipher
    )


def lock_default_for_publication(
    session: Session,
    capability: CapabilityValue,
    resolved: ResolvedModel | None,
) -> None:
    """Fence configuration writers until the caller's publication commits.

    Writers take the default row before the configuration row. The no-op UPDATE
    also obtains a SQLite write lock, where SELECT FOR UPDATE has no effect.
    It preserves both the public revision and the modification timestamp.
    """
    capability = _capability(capability)
    row = _default_row(session, capability)
    session.execute(
        update(AiModelDefault)
        .where(AiModelDefault.capability == capability)
        .values(
            revision=AiModelDefault.revision,
            updated_at=AiModelDefault.updated_at,
        )
        .execution_options(synchronize_session=False)
    )
    session.expire(row)
    current = (
        resolved.capability == capability and is_current(session, resolved)
        if resolved is not None
        else get_default_model(session, capability) is None
    )
    if not current:
        raise KGError(
            ErrorCode.REVISION_CONFLICT, {"reason": "model_configuration_changed"}
        )


def set_default(
    session: Session,
    capability: CapabilityValue,
    config_id: int | None,
    if_match: int,
) -> AiModelDefault:
    capability = _capability(capability)
    row = _default_row(session, capability)
    if row.revision != if_match:
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {
                "resource": "ai_model_default",
                "expected": row.revision,
                "actual": if_match,
            },
        )
    if config_id is not None:
        # Selection row is already locked; keep the global lock order.
        item = _config(session, config_id, lock=True)
        if item.capability != capability:
            raise _invalid("capability_mismatch", "config_id")
        if not item.enabled or not item.credential_cipher:
            raise _invalid("config_must_be_enabled_with_key", "config_id")
    if row.config_id != config_id:
        row = _advance_default(session, row, config_id)
    session.flush()
    return row
