"""M-06 安全 RDF 预解析、冲突预览和显式解决后的草稿装配。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from rdflib import OWL, RDF, RDFS, SKOS, Graph, URIRef
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.ontology_service import get_ontology, lock_ontology_edit
from app.models.domain import OntologyResourceRef
from app.models.enums import ResourceKind, ResourceStatus
from app.models.resource import ModelResource
from app.schemas.ontology import OntologyExportFormat
from app.schemas.ontology_import import (
    ImportFormat,
    ImportResourcePreview,
    OntologyImportApplyRequest,
    OntologyImportConflict,
    OntologyImportPreview,
    OntologyImportResult,
)

_MAX_BYTES = 64 * 1024
_MAX_TRIPLES = 2_000
_KG_KIND = URIRef("urn:knowledge:semantics:resourceKind")
_KIND_BY_RDF_TYPE = {
    OWL.Class: ResourceKind.ENTITY,
    OWL.DatatypeProperty: ResourceKind.DATATYPE_PROP,
    OWL.ObjectProperty: ResourceKind.OBJECT_PROP,
    SKOS.Collection: ResourceKind.DOMAIN,
}


@dataclass(frozen=True)
class ParsedImport:
    format: str
    graph: Graph
    root_iri: str | None
    resources: tuple[ImportResourcePreview, ...]
    conflicts: tuple[OntologyImportConflict, ...]


def _invalid(reason: str, **params: object) -> KGError:
    return KGError(ErrorCode.VALIDATION_VIOLATION, {"reason": reason, **params})


def _validate_jsonld_context(content: str) -> None:
    try:
        document = json.loads(content)
    except json.JSONDecodeError as exc:
        raise _invalid("invalid_json_ld") from exc

    def inspect_context(value: Any) -> None:
        if isinstance(value, str):
            raise _invalid("external_json_ld_context")
        if isinstance(value, list):
            for item in value:
                inspect_context(item)
        elif isinstance(value, dict) and value.get("@context") is not None:
            inspect_context(value["@context"])

    if isinstance(document, list):
        for item in document:
            if isinstance(item, dict) and "@context" in item:
                inspect_context(item["@context"])
    elif isinstance(document, dict) and "@context" in document:
        inspect_context(document["@context"])


def _parse(rdf_format: str, content: str) -> Graph:
    if len(content.encode("utf-8")) > _MAX_BYTES:
        raise _invalid("import_too_large", max_bytes=_MAX_BYTES)
    if rdf_format == OntologyExportFormat.JSON_LD.value:
        _validate_jsonld_context(content)
    graph = Graph()
    try:
        graph.parse(data=content, format=rdf_format)
    except Exception as exc:
        raise _invalid("invalid_rdf", format=rdf_format) from exc
    if len(graph) > _MAX_TRIPLES:
        raise _invalid("too_many_triples", max_triples=_MAX_TRIPLES)
    if (None, OWL.imports, None) in graph:
        raise _invalid("owl_imports_not_allowed")
    return graph


def _labels(graph: Graph, subject: URIRef) -> dict[str, str]:
    labels: dict[str, str] = {}
    for literal in graph.objects(subject, RDFS.label):
        language = str(getattr(literal, "language", "") or "")
        if language in {"zh", "zh-Hans", "zh-CN"}:
            labels["zh-CN"] = str(literal)
        elif language in {"en", "en-US"}:
            labels["en-US"] = str(literal)
    return labels


def _resource_kind(graph: Graph, subject: URIRef) -> ResourceKind | None:
    value = next(iter(graph.objects(subject, _KG_KIND)), None)
    if value is not None:
        try:
            return ResourceKind(str(value))
        except ValueError:
            return None
    for rdf_type, kind in _KIND_BY_RDF_TYPE.items():
        if (subject, RDF.type, rdf_type) in graph:
            return kind
    return None


def _parse_resources(graph: Graph) -> tuple[str | None, list[ImportResourcePreview]]:
    roots = [
        str(subject)
        for subject in graph.subjects(RDF.type, OWL.Ontology)
        if isinstance(subject, URIRef)
    ]
    root_iri = sorted(roots)[0] if roots else None
    subjects = (
        {
            subject
            for subject in graph.subjects(RDFS.isDefinedBy, URIRef(root_iri))
            if isinstance(subject, URIRef)
        }
        if root_iri
        else set()
    )
    if not subjects:
        subjects = {
            subject
            for subject in graph.subjects()
            if isinstance(subject, URIRef)
            and _resource_kind(graph, subject) is not None
        }
    resources = [
        ImportResourcePreview(
            iri=str(subject),
            kind=_resource_kind(graph, subject),
            label_i18n=_labels(graph, subject),
        )
        for subject in sorted(subjects, key=str)
    ]
    return root_iri, resources


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
    graph = _parse(rdf_format, content)
    root_iri, resources = _parse_resources(graph)
    conflicts = _preview_conflicts(session, resources, ontology_id)
    return OntologyImportPreview(
        format=rdf_format,
        root_iri=root_iri,
        triple_count=len(graph),
        resources=resources,
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
