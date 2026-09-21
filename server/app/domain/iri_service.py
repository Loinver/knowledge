"""命名空间与 IRI 治理（H-03）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.iri import build_iri, is_valid_name, is_valid_namespace
from app.models.resource import Namespace, ResourceRef
from app.schemas.common import ImpactItem


def register_namespace(
    session: Session,
    prefix: str,
    iri: str,
    protected: bool = False,
    label_i18n: dict | None = None,
) -> Namespace:
    """注册命名空间前缀。prefix/iri 唯一；protected 不可删。"""
    if not is_valid_namespace(iri):
        raise KGError(ErrorCode.INVALID_NAMESPACE, {"namespace": iri})
    existing = session.execute(
        select(Namespace).where((Namespace.prefix == prefix) | (Namespace.iri == iri))
    ).scalar_one_or_none()
    if existing is not None:
        raise KGError(
            ErrorCode.ALREADY_PUBLISHED,
            {"prefix": prefix, "reason": "namespace_exists"},
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
    session.delete(ns)
    session.flush()
