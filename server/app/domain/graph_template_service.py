"""视图模板（H-33 第二批）：形态配置持久化 + 本体版本失效检测。

模板钉住创建时的本体版本；本体发布更新版本后 stale=True，
前端显式提示"模板基于旧版本本体"，不静默沿用。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.ontology_snapshot import load_ontology_snapshot
from app.models.domain import Ontology
from app.models.enums import ResourceKind, ResourceStatus
from app.models.governance import ViewTemplate
from app.schemas.graph_view import (
    SemanticViewConfig,
    SemanticViewField,
    SemanticViewFieldsOut,
    ViewTemplateCreate,
)

MAX_PAGE_SIZE = 200
NUMERIC_DATATYPES = {"integer", "decimal", "float", "double", "number"}
TIME_DATATYPES = {"date", "datetime", "dateTime"}


def semantic_fields(
    session: Session, ontology_id: int, revision: int
) -> SemanticViewFieldsOut:
    """Read only pinned snapshots, including inherited properties' frozen names."""
    onto = session.get(Ontology, ontology_id)
    if onto is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"ontology_id": ontology_id})
    snapshots = load_ontology_snapshot(session, ontology_id, revision)
    fields: list[SemanticViewField] = []
    for resource in snapshots.values():
        if resource.kind == ResourceKind.OBJECT_PROP:
            fields.append(
                SemanticViewField(
                    iri=resource.iri,
                    name=resource.name,
                    label_i18n=resource.label_i18n or {},
                    kind="RELATION",
                )
            )
        if resource.kind not in {ResourceKind.ENTITY, ResourceKind.ASSOC}:
            continue
        pending = [resource.id]
        seen: set[int] = set()
        by_iri: dict[str, SemanticViewField] = {}
        while pending:
            resource_id = pending.pop(0)
            if resource_id in seen:
                continue
            seen.add(resource_id)
            parent = snapshots.get(resource_id)
            if parent is None:
                raise KGError(
                    ErrorCode.VALIDATION_VIOLATION,
                    {
                        "reason": "incomplete_snapshot_closure",
                        "resource_id": resource_id,
                    },
                )
            pending.extend(parent.parent_ids)
            for prop in parent.datatype_props:
                by_iri.setdefault(
                    prop.iri,
                    SemanticViewField(
                        iri=prop.iri,
                        name=prop.name,
                        kind="PROPERTY",
                        datatype=prop.datatype,
                        type_iri=resource.iri,
                        type_name=resource.name,
                    ),
                )
        fields.extend(by_iri.values())
    return SemanticViewFieldsOut(
        ontology_id=ontology_id,
        ontology_revision=revision,
        stale=onto.status != ResourceStatus.PUBLISHED
        or onto.current_revision != revision,
        fields=fields,
    )


def _validate_config(
    config: SemanticViewConfig, fields: list[SemanticViewField]
) -> None:
    for key, datatypes in (
        ("hierarchy_relation_iri", None),
        ("measure_property_iri", NUMERIC_DATATYPES),
        ("time_property_iri", TIME_DATATYPES),
        ("latitude_property_iri", NUMERIC_DATATYPES),
        ("longitude_property_iri", NUMERIC_DATATYPES),
    ):
        iri = getattr(config, key)
        if iri is None:
            continue
        matches = [field for field in fields if field.iri == iri]
        if not matches or any(
            (field.kind != "RELATION")
            if datatypes is None
            else (field.kind != "PROPERTY" or field.datatype not in datatypes)
            for field in matches
        ):
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {"field": key, "iri": iri, "reason": "invalid_semantic_field"},
            )
    if bool(config.latitude_property_iri) != bool(config.longitude_property_iri):
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION, {"reason": "coordinate_pair_required"}
        )


def create_template(session: Session, payload: ViewTemplateCreate) -> ViewTemplate:
    onto = session.scalar(
        select(Ontology)
        .where(Ontology.id == payload.ontology_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if onto is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND, {"ontology_id": payload.ontology_id}
        )
    if onto.status != ResourceStatus.PUBLISHED:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"ontology_id": onto.id, "reason": "ontology_not_published"},
        )
    if onto.current_revision != payload.ontology_revision:
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {"expected": payload.ontology_revision, "actual": onto.current_revision},
        )
    catalog = semantic_fields(session, onto.id, payload.ontology_revision)
    _validate_config(payload.config, catalog.fields)
    template = ViewTemplate(
        name_i18n=payload.name_i18n,
        layout_id=payload.layout_id,
        config=payload.config.model_dump(exclude_unset=True),
        ontology_id=payload.ontology_id,
        ontology_revision=payload.ontology_revision,
    )
    session.add(template)
    session.flush()
    return template


def list_templates(
    session: Session, ontology_id: int | None = None, page: int = 1, page_size: int = 50
) -> tuple[list[ViewTemplate], int]:
    stmt = select(ViewTemplate)
    if ontology_id is not None:
        stmt = stmt.where(ViewTemplate.ontology_id == ontology_id)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    items = list(
        session.scalars(
            stmt.order_by(ViewTemplate.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return items, total


def get_template(session: Session, template_id: int) -> ViewTemplate:
    template = session.get(ViewTemplate, template_id)
    if template is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"view_template_id": template_id})
    return template


def delete_template(session: Session, template_id: int) -> None:
    session.delete(get_template(session, template_id))
    session.flush()


def template_stale(session: Session, template: ViewTemplate) -> bool:
    """本体已发布比模板钉扎版本更新的版本 → 失效。"""
    onto = session.get(Ontology, template.ontology_id)
    if onto is None:
        return True
    return (
        onto.status != ResourceStatus.PUBLISHED
        or onto.current_revision != template.ontology_revision
    )


def applicable_template(
    session: Session, template_id: int, ontology_id: int, revision: int
) -> ViewTemplate:
    template = get_template(session, template_id)
    if (
        template_stale(session, template)
        or template.ontology_id != ontology_id
        or template.ontology_revision != revision
    ):
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {"view_template_id": template_id, "reason": "stale_view_template"},
        )
    catalog = semantic_fields(session, ontology_id, revision)
    _validate_config(SemanticViewConfig.model_validate(template.config), catalog.fields)
    return template
