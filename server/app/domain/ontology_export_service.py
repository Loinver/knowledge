"""M-07：选择并校验已发布本体快照，不回退到可变资源。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.ontology_service import get_ontology
from app.domain.status_service import get_revision
from app.models.domain import OntologyRevision
from app.models.enums import ResourceKind
from app.schemas.ontology import OntologyExportFormat
from app.semantics.ontology_rdf import (
    OntologyRdfMetadata,
    OntologyRdfResource,
    serialize_ontology_rdf,
)


@dataclass(frozen=True)
class OntologyExport:
    content: str
    media_type: str
    filename: str


def _violation(resource_id: int, reason: str, **params: object) -> KGError:
    return KGError(
        ErrorCode.VALIDATION_VIOLATION,
        {"resource_id": resource_id, "reason": reason, **params},
    )


def export_ontology(
    session: Session,
    ontology_id: int,
    rdf_format: OntologyExportFormat = OntologyExportFormat.TURTLE,
    revision: int | None = None,
) -> OntologyExport:
    """默认导出最近发布版本；草稿修改不影响历史导出。"""
    onto = get_ontology(session, ontology_id)
    revision = onto.current_revision if revision is None else revision
    if revision < 1:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"ontology_id": ontology_id, "reason": "ontology_not_published"},
        )
    published = session.scalar(
        select(OntologyRevision).where(
            OntologyRevision.ontology_id == ontology_id,
            OntologyRevision.revision == revision,
        )
    )
    if published is None:
        raise KGError(
            ErrorCode.REVISION_NOT_FOUND,
            {"ontology_id": ontology_id, "revision": revision},
        )
    missing_metadata = sorted(
        set(OntologyRdfMetadata.model_fields) - published.metadata_snapshot.keys()
    )
    if missing_metadata:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {
                "ontology_id": ontology_id,
                "revision": revision,
                "reason": "missing_ontology_metadata_snapshot",
                "fields": missing_metadata,
            },
        )
    try:
        metadata = OntologyRdfMetadata.model_validate(published.metadata_snapshot)
    except ValidationError as exc:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {
                "ontology_id": ontology_id,
                "reason": "invalid_ontology_metadata_snapshot",
            },
        ) from exc

    snapshots: dict[int, OntologyRdfResource] = {}
    for resource_id, pinned_revision in published.resource_versions.items():
        rid = int(resource_id)
        frozen = get_revision(session, rid, pinned_revision)
        required = {"parent_ids", "resource_refs", "namespace"}
        missing = sorted(required - frozen.payload.keys())
        if missing:
            raise _violation(rid, "missing_snapshot_structure", fields=missing)
        try:
            snapshots[rid] = OntologyRdfResource.model_validate(frozen.payload)
        except ValidationError as exc:
            raise _violation(rid, "invalid_snapshot_structure") from exc

    for rid, snapshot in snapshots.items():
        if not snapshot.namespace.get("prefix") or not snapshot.namespace.get("iri"):
            raise _violation(rid, "missing_snapshot_namespace")
        for parent_id in snapshot.parent_ids:
            parent = _target(snapshots, rid, parent_id)
            if snapshot.kind not in (ResourceKind.ENTITY, ResourceKind.ASSOC) or (
                parent.kind not in (ResourceKind.ENTITY, ResourceKind.ASSOC)
            ):
                raise _violation(rid, "invalid_parent_kind", target_id=parent_id)
        _validate_references(rid, snapshot, snapshots)

    content = serialize_ontology_rdf(
        metadata, snapshots, revision=revision, rdf_format=rdf_format
    )
    filename = re.sub(r"[^A-Za-z0-9_-]+", "-", metadata.name).strip("-") or "ontology"
    if rdf_format == OntologyExportFormat.TURTLE:
        return OntologyExport(content, "text/turtle", f"{filename}-r{revision}.ttl")
    return OntologyExport(
        content, "application/ld+json", f"{filename}-r{revision}.jsonld"
    )


def _target(
    snapshots: dict[int, OntologyRdfResource], resource_id: int, target_id: int
) -> OntologyRdfResource:
    target = snapshots.get(target_id)
    if target is None:
        raise _violation(
            resource_id, "incomplete_snapshot_closure", target_id=target_id
        )
    return target


def _validate_references(
    resource_id: int,
    snapshot: OntologyRdfResource,
    snapshots: dict[int, OntologyRdfResource],
) -> None:
    endpoint_roles: set[str] = set()
    for ref in snapshot.resource_refs:
        target = _target(snapshots, resource_id, ref.target_id)
        if ref.role in {"relation_domain", "relation_range"}:
            if snapshot.kind != ResourceKind.OBJECT_PROP or (
                target.kind != ResourceKind.ENTITY
            ):
                raise _violation(resource_id, "invalid_endpoint_kind", role=ref.role)
            endpoint_roles.add(ref.role)
        elif ref.role in {"data_prop", "assoc_attribute"}:
            if snapshot.kind not in (ResourceKind.ENTITY, ResourceKind.ASSOC) or (
                target.kind != ResourceKind.DATATYPE_PROP
            ):
                raise _violation(resource_id, "invalid_attribute_kind", role=ref.role)
        elif ref.role == "inverse_of":
            if snapshot.kind != ResourceKind.OBJECT_PROP or (
                target.kind != ResourceKind.OBJECT_PROP
            ):
                raise _violation(resource_id, "invalid_inverse_kind")
        elif ref.role == "assoc_resource":
            if snapshot.kind != ResourceKind.OBJECT_PROP or (
                target.kind != ResourceKind.ASSOC
            ):
                raise _violation(resource_id, "invalid_association_kind")
        else:
            raise _violation(resource_id, "unsupported_reference_role", role=ref.role)
    if snapshot.kind == ResourceKind.OBJECT_PROP and endpoint_roles != {
        "relation_domain",
        "relation_range",
    }:
        raise _violation(resource_id, "missing_relation_endpoints")
