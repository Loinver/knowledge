"""HTTP 写操作的审计边界。成功随业务提交，失败先回滚再独立留痕。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, TypeVar
from uuid import uuid4

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from sqlalchemy import Connection, Engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, SessionTransaction

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.asset_audit_service import read_asset_version, record_asset_audit
from app.models.asset_audit import AssetAuditAction, AssetType
from app.models.enums import AuditResult

_F = TypeVar("_F", bound=Callable[..., Any])
_KEY = "asset_audit_context"
_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssetAuditSpec:
    action: AssetAuditAction
    object_type: AssetType
    id_parameter: str | None


@dataclass
class _AuditContext:
    spec: AssetAuditSpec
    actor_id: str
    correlation_id: str
    object_id: int | None
    version_before: dict[str, int | None] | None = None
    captured_before: bool = False
    committed: bool = False


def audit_asset(
    action: AssetAuditAction, object_type: AssetType, id_parameter: str | None = None
) -> Callable[[_F], _F]:
    """声明审计语义，不包装函数、不更改 FastAPI 签名或事务。"""

    def decorate(endpoint: _F) -> _F:
        endpoint.asset_audit_spec = AssetAuditSpec(  # type: ignore[attr-defined]
            action, object_type, id_parameter
        )
        return endpoint

    return decorate


def audit_created(session: Session, object_id: int) -> None:
    """创建操作在提交前提供服务器分配的主键。独立领域测试无需 HTTP 上下文。"""
    context: _AuditContext | None = session.info.get(_KEY)
    if context is not None:
        if context.spec.id_parameter is not None or context.object_id is not None:
            raise RuntimeError("Audit target is already bound")
        if object_id < 1:
            raise RuntimeError("Audit target must be persisted")
        context.object_id = object_id


def _failure_code(exc: Exception) -> ErrorCode:
    if isinstance(exc, KGError):
        return exc.code
    if isinstance(exc, RequestValidationError):
        return ErrorCode.INVALID_REQUEST
    if isinstance(exc, SQLAlchemyError):
        return ErrorCode.DATABASE_ERROR
    return ErrorCode.INTERNAL_ERROR


@contextmanager
def business_asset_audit(
    request: Request, response: Response, session: Session, actor_id: str
) -> Iterator[None]:
    endpoint = request.scope.get("endpoint")
    spec = getattr(endpoint, "asset_audit_spec", None)
    if not isinstance(spec, AssetAuditSpec):
        yield
        return

    object_id = None
    if spec.id_parameter is not None:
        raw_id = str(request.path_params.get(spec.id_parameter, ""))
        # Route parameters have not necessarily passed FastAPI validation yet.
        if (
            len(raw_id) <= 19
            and raw_id.isascii()
            and raw_id.isdecimal()
            and 0 < int(raw_id) <= 2**63 - 1
        ):
            object_id = int(raw_id)
    context = _AuditContext(spec, actor_id, uuid4().hex, object_id)
    request.state.asset_audit_correlation_id = context.correlation_id
    response.headers["X-Correlation-ID"] = context.correlation_id
    session.info[_KEY] = context
    bind = session.get_bind()
    engine = bind if isinstance(bind, Engine) else bind.engine

    def capture_before(
        _session: Session, transaction: SessionTransaction, connection: Connection
    ) -> None:
        if not context.captured_before and transaction.parent is None:
            context.captured_before = True
            if spec.id_parameter is not None:
                context.version_before = read_asset_version(
                    connection, spec.object_type, context.object_id, lock=True
                )

    def before_commit(active: Session) -> None:
        if context.committed:
            raise RuntimeError("An audited operation may commit only once")
        if context.object_id is None:
            raise RuntimeError("Audited write has no persisted target")
        active.flush()
        after = read_asset_version(
            active.connection(), spec.object_type, context.object_id
        )
        record_asset_audit(
            active,
            actor_id=context.actor_id,
            action=spec.action,
            object_type=spec.object_type,
            object_id=context.object_id,
            version_before=context.version_before,
            version_after=after,
            result=AuditResult.OK,
            correlation_id=context.correlation_id,
        )

    def after_commit(_session: Session) -> None:
        context.committed = True

    event.listen(session, "after_begin", capture_before)
    event.listen(session, "before_commit", before_commit)
    event.listen(session, "after_commit", after_commit)
    try:
        yield
    except Exception as exc:
        # A post-commit response failure must not fabricate a rolled-back mutation.
        if not context.committed:
            session.rollback()
            # At most one attempt for an authenticated, explicitly registered action.
            # No request/body/headers/exception text crosses this boundary. A separate
            # session cannot flush pending business objects from the failed request.
            try:
                with Session(bind=engine) as failure_session, failure_session.begin():
                    record_asset_audit(
                        failure_session,
                        actor_id=context.actor_id,
                        action=spec.action,
                        object_type=spec.object_type,
                        # A rolled-back creation does not own the allocated ID.
                        object_id=context.object_id if spec.id_parameter else None,
                        version_before=context.version_before,
                        version_after=None,
                        result=AuditResult.FAILED,
                        correlation_id=context.correlation_id,
                        error_code=_failure_code(exc),
                    )
            except SQLAlchemyError:
                # No retry loop or exception/SQL payload logging on a failing database.
                _log.error(
                    "asset_audit_write_failed correlation=%s", context.correlation_id
                )
        raise
    finally:
        event.remove(session, "after_begin", capture_before)
        event.remove(session, "before_commit", before_commit)
        event.remove(session, "after_commit", after_commit)
        session.info.pop(_KEY, None)
