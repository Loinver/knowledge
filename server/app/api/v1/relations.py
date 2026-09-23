"""关系类型库路由（H-12）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.governance_common import governance_session as get_session
from app.domain.relation_service import (
    create_relation_type,
    get_assoc_attributes,
    get_relation_meta,
    get_relation_type,
    list_relation_types,
    publish_relation_type,
    update_relation_type,
)
from app.models.resource import ModelResource
from app.schemas.relation import (
    AttributeDefOut,
    CardinalitySpec,
    EndpointSpec,
    OwlFeatures,
    RelationTypeBrief,
    RelationTypeCreate,
    RelationTypeOut,
    RelationTypeUpdate,
)
from app.schemas.response import ApiResponse
from app.schemas.type import RevisionOut as TypeRevisionOut

router = APIRouter(prefix="/relations", tags=["relations"])


def _to_out(session: Session, resource: ModelResource) -> RelationTypeOut:
    """组装 RelationTypeOut。

    端点基数、角色标签与 OWL 特征一律从存储读回（M-07 补齐正式列），
    不再区分「创建时用 payload、其余按默认值猜」两条路径。
    """
    meta = get_relation_meta(session, resource)
    domain_id = meta["domain_ids"][0] if meta["domain_ids"] else 0
    range_id = meta["range_ids"][0] if meta["range_ids"] else 0
    domain_spec = EndpointSpec(
        type_id=domain_id,
        cardinality=CardinalitySpec(
            min=meta["domain_min"],
            max=meta["domain_max"],
            role_label_i18n=meta["domain_cardinality_role_i18n"],
        ),
        role_i18n=meta["domain_role_i18n"],
    )
    range_spec = EndpointSpec(
        type_id=range_id,
        cardinality=CardinalitySpec(
            min=meta["range_min"],
            max=meta["range_max"],
            role_label_i18n=meta["range_cardinality_role_i18n"],
        ),
        role_i18n=meta["range_role_i18n"],
    )

    attribute_defs: list[AttributeDefOut] = []
    if meta["assoc_resource_id"] is not None:
        attribute_defs = get_assoc_attributes(session, meta["assoc_resource_id"])

    return RelationTypeOut(
        id=resource.id,
        kind=resource.kind,
        name=resource.name,
        iri=resource.iri,
        namespace_id=resource.namespace_id,
        label_i18n=resource.label_i18n,
        definition_i18n=resource.definition_i18n,
        status=resource.status,
        current_revision=resource.current_revision,
        edit_revision=resource.edit_revision,
        domain_spec=domain_spec,
        range_spec=range_spec,
        inverse_of=meta["inverse_of"],
        owl=OwlFeatures(**meta["owl"]),
        union_of=meta["union_of"],
        intersection_of=meta["intersection_of"],
        enable_attributes=meta["assoc_resource_id"] is not None,
        assoc_resource_id=meta["assoc_resource_id"],
        attribute_defs=attribute_defs,
    )


@router.get("", response_model=ApiResponse[list[RelationTypeBrief]])
def list_relations(
    q: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[RelationTypeBrief]:
    items, _total = list_relation_types(session, q, page, page_size)
    out: list[RelationTypeBrief] = []
    for res in items:
        meta = get_relation_meta(session, res)
        out.append(
            RelationTypeBrief(
                id=res.id,
                name=res.name,
                iri=res.iri,
                label_i18n=res.label_i18n,
                status=res.status,
                current_revision=res.current_revision,
                enable_attributes=meta["assoc_resource_id"] is not None,
                inverse_of=meta["inverse_of"],
            )
        )
    return out


@router.post("", response_model=ApiResponse[RelationTypeOut], status_code=201)
def create_relation(
    payload: RelationTypeCreate, session: Session = Depends(get_session)
) -> RelationTypeOut:
    resource = create_relation_type(session, payload)
    session.commit()
    return _to_out(session, resource)


@router.get("/{relation_id}", response_model=ApiResponse[RelationTypeOut])
def get_relation(
    relation_id: int, session: Session = Depends(get_session)
) -> RelationTypeOut:
    resource = get_relation_type(session, relation_id)
    return _to_out(session, resource)


@router.put("/{relation_id}", response_model=ApiResponse[RelationTypeOut])
def update_relation(
    relation_id: int,
    payload: RelationTypeUpdate,
    session: Session = Depends(get_session),
) -> RelationTypeOut:
    resource = get_relation_type(session, relation_id)
    update_relation_type(session, resource, payload)
    session.commit()
    return _to_out(session, resource)


@router.post("/{relation_id}/publish", response_model=ApiResponse[TypeRevisionOut])
def publish_relation(
    relation_id: int, session: Session = Depends(get_session)
) -> TypeRevisionOut:
    resource = get_relation_type(session, relation_id)
    revision = publish_relation_type(session, resource)
    session.commit()
    return TypeRevisionOut(revision=revision, checksum="")
