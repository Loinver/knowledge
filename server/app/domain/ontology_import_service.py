"""M-06 导入资源匹配、冲突预览和显式解决后的草稿装配。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.ontology_service import get_ontology, lock_ontology_edit
from app.models.domain import OntologyResourceRef
from app.models.enums import ResourceStatus
from app.models.resource import ModelResource
from app.schemas.ontology_import import (
    ImportFormat,
    ImportResourcePreview,
    OntologyImportApplyRequest,
    OntologyImportConflict,
    OntologyImportPreview,
    OntologyImportResult,
)
from app.semantics.ontology_rdf import parse_ontology_rdf


def _preview_conflicts(
    session: Session,
    resources: list[ImportResourcePreview],
    ontology_id: int | None,
) -> list[OntologyImportConflict]:
    conflicts: list[OntologyImportConflict] = []
    refs = {}
    if ontology_id is not None:
        refs = {
            ref.resource_id: ref
            for ref in session.scalars(
                select(OntologyResourceRef).where(
                    OntologyResourceRef.ontology_id == ontology_id
                )
            )
        }
    for resource in resources:
        existing = session.scalar(
            select(ModelResource).where(ModelResource.iri == resource.iri)
        )
        if existing is None:
            resource.conflict_codes.append("UNKNOWN_RESOURCE")
            conflicts.append(
                OntologyImportConflict(iri=resource.iri, code="UNKNOWN_RESOURCE")
            )
            continue
        resource.existing_resource_id = existing.id
        resource.existing_revision = existing.current_revision
        if resource.kind is not None and existing.kind != resource.kind:
            resource.conflict_codes.append("KIND_MISMATCH")
            conflicts.append(
                OntologyImportConflict(
                    iri=resource.iri,
                    code="KIND_MISMATCH",
                    params={
                        "existing_kind": existing.kind.value,
                        "imported_kind": resource.kind.value,
                    },
                )
            )
        ref = refs.get(existing.id)
        if ref is not None and ref.pinned_revision not in (
            None,
            existing.current_revision,
        ):
            resource.conflict_codes.append("TARGET_REVISION_CONFLICT")
            conflicts.append(
                OntologyImportConflict(
                    iri=resource.iri,
                    code="TARGET_REVISION_CONFLICT",
                    params={
                        "existing_revision": ref.pinned_revision,
                        "latest_revision": existing.current_revision,
                    },
                )
            )
    return conflicts


def preview_import(
    session: Session,
    rdf_format: ImportFormat,
    content: str,
    ontology_id: int | None = None,
) -> OntologyImportPreview:
    parsed = parse_ontology_rdf(rdf_format, content)
    conflicts = _preview_conflicts(session, parsed.resources, ontology_id)
    return OntologyImportPreview(
        format=rdf_format,
        root_iri=parsed.root_iri,
        triple_count=parsed.triple_count,
        resources=parsed.resources,
        conflicts=conflicts,
        requires_resolution=bool(conflicts),
    )


def apply_import(
    session: Session,
    payload: OntologyImportApplyRequest,
    revision: int,
    if_edit_match: int | None = None,
) -> OntologyImportResult:
    ontology = get_ontology(session, payload.ontology_id)
    ontology = lock_ontology_edit(session, ontology, if_edit_match, if_match=revision)
    if ontology.status != ResourceStatus.DRAFT:
        raise KGError(ErrorCode.ALREADY_PUBLISHED, {"ontology_id": ontology.id})
    parsed = preview_import(
        session, payload.format, payload.content, payload.ontology_id
    )
    resolution_map = {item.iri: item for item in payload.resolutions}
    missing = [
        conflict.iri
        for conflict in parsed.conflicts
        if conflict.iri not in resolution_map
    ]
    if missing:
        raise KGError(
            ErrorCode.INVALID_REQUEST,
            {"reason": "import_resolution_required", "iris": missing},
        )
    refs = {
        ref.resource_id: ref
        for ref in session.scalars(
            select(OntologyResourceRef).where(
                OntologyResourceRef.ontology_id == ontology.id
            )
        )
    }
    added: list[int] = []
    skipped: list[str] = []
    for item in parsed.resources:
        resolution = resolution_map.get(item.iri)
        if resolution is not None and resolution.action == "SKIP":
            skipped.append(item.iri)
            continue
        if item.existing_resource_id is None:
            raise KGError(
                ErrorCode.INVALID_REQUEST,
                {"reason": "unknown_resource_requires_skip", "iri": item.iri},
            )
        if resolution is not None and resolution.resource_id not in (
            None,
            item.existing_resource_id,
        ):
            raise KGError(
                ErrorCode.INVALID_REQUEST,
                {"reason": "resolution_resource_mismatch", "iri": item.iri},
            )
        if item.existing_resource_id in refs:
            continue
        session.add(
            OntologyResourceRef(
                ontology_id=ontology.id,
                resource_id=item.existing_resource_id,
                pinned_revision=item.existing_revision or None,
            )
        )
        added.append(item.existing_resource_id)
    session.flush()
    return OntologyImportResult(
        ontology_id=ontology.id,
        root_iri=parsed.root_iri,
        added_resource_ids=added,
        skipped_iris=skipped,
        triple_count=parsed.triple_count,
    )
