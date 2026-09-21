"""命名空间与 IRI 治理路由（H-03）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.iri_service import (
    delete_namespace,
    register_namespace,
    scan_rename_impact,
)
from app.iri import build_iri, is_valid_name, is_valid_namespace
from app.models.resource import Namespace
from app.schemas.common import (
    ImpactResponse,
    IriBuildRequest,
    IriBuildResponse,
    IriValidateResponse,
    NamespaceCreate,
    NamespaceOut,
)

router = APIRouter(prefix="/namespaces", tags=["namespaces"])


@router.get("", response_model=list[NamespaceOut])
def list_namespaces(session: Session = Depends(get_session)) -> list[Namespace]:
    return list(session.execute(select(Namespace).order_by(Namespace.prefix)).scalars())


@router.post("", response_model=NamespaceOut, status_code=201)
def create_namespace(
    payload: NamespaceCreate, session: Session = Depends(get_session)
) -> Namespace:
    ns = register_namespace(
        session, payload.prefix, payload.iri, payload.protected, payload.label_i18n
    )
    session.commit()
    return ns


@router.delete("/{namespace_id}", status_code=204)
def remove_namespace(
    namespace_id: int, session: Session = Depends(get_session)
) -> None:
    delete_namespace(session, namespace_id)
    session.commit()


@router.get("/iri/build", response_model=IriBuildResponse)
def build_iri_endpoint(payload: IriBuildRequest) -> IriBuildResponse:
    """直接按命名空间 IRI + 机读名拼接，不查库。"""
    return IriBuildResponse(iri=build_iri(payload.namespace, payload.name))


@router.get("/iri/validate", response_model=IriValidateResponse)
def validate_iri_endpoint(name: str, namespace: str = "") -> IriValidateResponse:
    return IriValidateResponse(
        name=is_valid_name(name), namespace=is_valid_namespace(namespace)
    )


@router.get("/iri/impact/{resource_id}", response_model=ImpactResponse)
def rename_impact(
    resource_id: int, session: Session = Depends(get_session)
) -> ImpactResponse:
    refs = scan_rename_impact(session, resource_id)
    return ImpactResponse(resource_id=resource_id, references=refs)
