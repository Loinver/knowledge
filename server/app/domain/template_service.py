"""模板维护、引用保护与已发布版本装配。"""

from __future__ import annotations

from copy import deepcopy

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.status_service import get_revision
from app.models.domain import AssemblyTemplate, Ontology, OntologyRevision
from app.models.resource import ModelResource, ResourceRevision
from app.schemas.template import (
    TemplateCreate,
    TemplateFromOntology,
    TemplateMetadata,
    TemplateOut,
    TemplateResource,
    TemplateResourceOption,
    TemplateResourcePage,
)


def get_template(session: Session, template_id: int) -> AssemblyTemplate:
    item = session.get(AssemblyTemplate, template_id, populate_existing=True)
    if item is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"template_id": template_id})
    return item


def lock_template(
    session: Session, template_id: int, revision: int | None = None
) -> AssemblyTemplate:
    """同一行写锁串行化删除、编辑和引用创建，也适用于 SQLite。"""
    statement = update(AssemblyTemplate).where(AssemblyTemplate.id == template_id)
    if revision is not None:
        statement = statement.where(AssemblyTemplate.revision == revision)
    found = session.scalar(
        statement.values(revision=AssemblyTemplate.revision)
        .returning(AssemblyTemplate.id)
        .execution_options(synchronize_session=False)
    )
    item = get_template(session, template_id)
    if found is None:
        raise KGError(
            ErrorCode.REVISION_CONFLICT,
            {"expected": revision, "actual": item.revision, "template_id": template_id},
        )
    return item


def template_resources(item: AssemblyTemplate) -> list[TemplateResource]:
    try:
        if not isinstance(item.payload, dict) or set(item.payload) - {"resources"}:
            raise ValueError("unsupported template payload")
        return [
            TemplateResource.model_validate(value)
            for value in item.payload.get("resources", [])
        ]
    except (ValueError, TypeError, AttributeError) as exc:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"reason": "invalid_template_resources", "template_id": item.id},
        ) from exc


def validate_resources(session: Session, resources: list[TemplateResource]) -> None:
    seen: set[int] = set()
    for ref in resources:
        if ref.resource_id in seen:
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {"reason": "duplicate_template_resource"},
            )
        seen.add(ref.resource_id)
        get_revision(session, ref.resource_id, ref.pinned_revision)


def template_out(session: Session, item: AssemblyTemplate) -> TemplateOut:
    count = (
        session.scalar(
            select(func.count())
            .select_from(Ontology)
            .where(Ontology.template_id == item.id)
        )
        or 0
    )
    return TemplateOut(
        id=item.id,
        name=item.name,
        label_i18n=item.label_i18n,
        source=item.source,
        basis=item.basis,
        builtin=item.builtin,
        revision=item.revision,
        resources=template_resources(item),
        reference_count=count,
    )


def list_templates(
    session: Session, q: str, builtin: bool | None, page: int, page_size: int
) -> tuple[list[AssemblyTemplate], int]:
    statement = select(AssemblyTemplate)
    if q:
        statement = statement.where(AssemblyTemplate.name.contains(q, autoescape=True))
    if builtin is not None:
        statement = statement.where(AssemblyTemplate.builtin == builtin)
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = list(
        session.scalars(
            statement.order_by(AssemblyTemplate.name, AssemblyTemplate.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return items, total


def create_template(session: Session, payload: TemplateCreate) -> AssemblyTemplate:
    validate_resources(session, payload.resources)
    item = AssemblyTemplate(
        **payload.model_dump(exclude={"resources"}),
        builtin=False,
        revision=1,
        payload={"resources": [ref.model_dump() for ref in payload.resources]},
    )
    session.add(item)
    session.flush()
    return item


def update_template(
    session: Session, template_id: int, revision: int, payload: TemplateCreate
) -> AssemblyTemplate:
    item = lock_template(session, template_id, revision)
    _editable(item)
    validate_resources(session, payload.resources)
    for key, value in payload.model_dump(exclude={"resources"}).items():
        setattr(item, key, value)
    item.payload = {"resources": [ref.model_dump() for ref in payload.resources]}
    item.revision += 1
    session.flush()
    return item


def _editable(item: AssemblyTemplate) -> None:
    if item.builtin:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION, {"reason": "template_builtin_readonly"}
        )


def delete_template(session: Session, template_id: int, revision: int) -> None:
    item = lock_template(session, template_id, revision)
    _editable(item)
    if session.scalar(
        select(Ontology.id).where(Ontology.template_id == template_id).limit(1)
    ):
        raise KGError(ErrorCode.VALIDATION_VIOLATION, {"reason": "template_in_use"})
    session.delete(item)
    session.flush()


def copy_template(
    session: Session, template_id: int, revision: int, payload: TemplateMetadata
) -> AssemblyTemplate:
    original = lock_template(session, template_id, revision)
    return create_template(
        session,
        TemplateCreate(
            **payload.model_dump(),
            resources=deepcopy(template_resources(original)),
        ),
    )


def from_ontology(session: Session, payload: TemplateFromOntology) -> AssemblyTemplate:
    published = session.scalar(
        select(OntologyRevision).where(
            OntologyRevision.ontology_id == payload.ontology_id,
            OntologyRevision.revision == payload.ontology_revision,
        )
    )
    if published is None:
        raise KGError(
            ErrorCode.REVISION_NOT_FOUND,
            {
                "ontology_id": payload.ontology_id,
                "revision": payload.ontology_revision,
            },
        )
    return create_template(
        session,
        TemplateCreate(
            **payload.model_dump(exclude={"ontology_id", "ontology_revision"}),
            resources=[
                TemplateResource(resource_id=int(rid), pinned_revision=rev)
                for rid, rev in published.resource_versions.items()
            ],
        ),
    )


def resource_catalog(
    session: Session, q: str, page: int, page_size: int
) -> TemplateResourcePage:
    statement = select(ModelResource).where(
        select(ResourceRevision.id)
        .where(ResourceRevision.resource_id == ModelResource.id)
        .exists()
    )
    if q:
        statement = statement.where(ModelResource.name.contains(q, autoescape=True))
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    resources = list(
        session.scalars(
            statement.order_by(ModelResource.name, ModelResource.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    items = [
        TemplateResourceOption(
            resource_id=item.id,
            name=item.name,
            iri=item.iri,
            kind=item.kind,
            label_i18n=item.label_i18n,
            revisions=list(
                session.scalars(
                    select(ResourceRevision.revision)
                    .where(ResourceRevision.resource_id == item.id)
                    .order_by(ResourceRevision.revision)
                )
            ),
        )
        for item in resources
    ]
    return TemplateResourcePage(
        items=items, total=total, page=page, page_size=page_size
    )
