"""命名空间与 IRI 治理（H-03）。"""

from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.iri import build_iri, is_valid_name, is_valid_namespace
from app.models.resource import ModelResource, Namespace, ResourceRef
from app.schemas.common import ImpactItem

# 前缀会出现在 Turtle/JSON-LD 的 `prefix:` 缩写里，限定为小写 NCName 子集，免转义。
PREFIX_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def list_namespaces(session: Session) -> list[Namespace]:
    """按前缀列出已注册命名空间。"""
    return list(session.scalars(select(Namespace).order_by(Namespace.prefix)))


def namespace_usage(session: Session) -> dict[int, int]:
    """各命名空间下的语义资源数，用于界面判断能否删除。"""
    rows = session.execute(
        select(ModelResource.namespace_id, func.count()).group_by(
            ModelResource.namespace_id
        )
    ).tuples()
    return dict(rows.all())


def register_namespace(
    session: Session,
    prefix: str,
    iri: str,
    protected: bool = False,
    label_i18n: dict | None = None,
) -> Namespace:
    """注册命名空间前缀。prefix/iri 唯一；protected 不可删。"""
    if not PREFIX_PATTERN.match(prefix):
        raise KGError(
            ErrorCode.INVALID_NAMESPACE, {"namespace": prefix, "field": "prefix"}
        )
    if not is_valid_namespace(iri):
        raise KGError(ErrorCode.INVALID_NAMESPACE, {"namespace": iri, "field": "iri"})
    existing = session.scalars(
        select(Namespace).where((Namespace.prefix == prefix) | (Namespace.iri == iri))
    ).first()
    if existing is not None:
        field = "prefix" if existing.prefix == prefix else "iri"
        raise KGError(
            ErrorCode.ALREADY_EXISTS,
            {"namespace": prefix if field == "prefix" else iri, "field": field},
        )
    ns = Namespace(prefix=prefix, iri=iri, protected=protected, label_i18n=label_i18n)
    session.add(ns)
    session.flush()
    return ns


def build_resource_iri(namespace: Namespace, name: str) -> str:
    """拼接命名空间 IRI 与机读名。"""
    return build_iri(namespace.iri, name)


def validate_name(name: str) -> None:
    """校验机读名合法性，不合法抛 KGError。"""
    if not is_valid_name(name):
        raise KGError(ErrorCode.INVALID_NAME, {"name": name})


def scan_rename_impact(session: Session, resource_id: int) -> list[ImpactItem]:
    """更名影响面扫描：返回引用该资源的全部 source。"""
    refs = (
        session.execute(select(ResourceRef).where(ResourceRef.target_id == resource_id))
        .scalars()
        .all()
    )
    return [ImpactItem(source_id=r.source_id, role=r.role, ref_id=r.id) for r in refs]


def delete_namespace(session: Session, namespace_id: int) -> None:
    """删除命名空间。protected=True 的核心命名空间不可删。"""
    ns = session.get(Namespace, namespace_id)
    if ns is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"id": namespace_id})
    if ns.protected:
        raise KGError(ErrorCode.PROTECTED_NAMESPACE, {"prefix": ns.prefix})
    # 资源 IRI 由命名空间推导，删掉仍被引用的命名空间会让已有资源失去 IRI 来源。
    count = session.scalar(
        select(func.count())
        .select_from(ModelResource)
        .where(ModelResource.namespace_id == namespace_id)
    )
    if count:
        raise KGError(ErrorCode.RESOURCE_IN_USE, {"prefix": ns.prefix, "count": count})
    session.delete(ns)
    session.flush()
