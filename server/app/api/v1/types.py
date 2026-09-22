"""实体类型库路由（H-11）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.governance_common import governance_session
from app.domain.type_service import (
    create_entity_type,
    get_data_props,
    get_entity_type,
    get_parent_ids,
    get_prop_detail,
    list_entity_types,
    publish_entity_type,
    update_entity_type,
)
from app.models.resource import ModelResource
from app.schemas.response import ApiResponse
from app.schemas.type import (
    DataTypePropOut,
    EntityTypeBrief,
    EntityTypeCreate,
    EntityTypeOut,
    EntityTypeUpdate,
    RevisionOut,
)

router = APIRouter(prefix="/entity-types", tags=["entity-types"])


def _data_props(session: Session, resource: ModelResource) -> list[DataTypePropOut]:
    """读回数据属性，含数据类型、枚举引用、可空与默认值（M-07 补齐）。

    历史行可能没有明细，此时回退到 string / nullable 的保守默认。
    """
    out: list[DataTypePropOut] = []
    for prop in get_data_props(session, resource):
        detail = get_prop_detail(session, prop.id)
        out.append(
            DataTypePropOut(
                name=detail.prop_name if detail else prop.name.split(".")[-1],
                label_i18n=prop.label_i18n,
                definition_i18n=prop.definition_i18n,
                datatype=detail.datatype if detail else "string",
                enum_dict_id=detail.enum_dict_id if detail else None,
                enum_dict_revision=detail.enum_dict_revision if detail else None,
                nullable=detail.nullable if detail else True,
                default_value=detail.default_value if detail else None,
            )
        )
    return out


def _out(session: Session, resource: ModelResource) -> EntityTypeOut:
    return EntityTypeOut(
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
        data_props=_data_props(session, resource),
        parent_ids=get_parent_ids(session, resource),
    )


@router.get("", response_model=ApiResponse[list[EntityTypeBrief]])
def list_types(
    q: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: Session = Depends(governance_session),
) -> list[EntityTypeBrief]:
    items, _total = list_entity_types(session, q, page, page_size)
    return [EntityTypeBrief.model_validate(i) for i in items]


@router.post("", response_model=ApiResponse[EntityTypeOut], status_code=201)
def create_type(
    payload: EntityTypeCreate, session: Session = Depends(governance_session)
) -> EntityTypeOut:
    resource = create_entity_type(session, payload)
    session.commit()
    return _out(session, resource)


@router.get("/{type_id}", response_model=ApiResponse[EntityTypeOut])
def get_type(
    type_id: int, session: Session = Depends(governance_session)
) -> EntityTypeOut:
    return _out(session, get_entity_type(session, type_id))


@router.put("/{type_id}", response_model=ApiResponse[EntityTypeOut])
def update_type(
    type_id: int,
    payload: EntityTypeUpdate,
    session: Session = Depends(governance_session),
) -> EntityTypeOut:
    resource = get_entity_type(session, type_id)
    update_entity_type(session, resource, payload)
    session.commit()
    return _out(session, resource)


@router.post("/{type_id}/publish", response_model=ApiResponse[RevisionOut])
def publish_type(
    type_id: int, session: Session = Depends(governance_session)
) -> RevisionOut:
    resource = get_entity_type(session, type_id)
    revision = publish_entity_type(session, resource)
    session.commit()
    return RevisionOut(revision=revision, checksum="")
