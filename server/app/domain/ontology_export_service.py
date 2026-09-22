"""M-07：只从已发布版本序列化本体，缺失快照不回退到可变资源。

urn:knowledge:ref:{role} 保留应用引用角色（包括关联实体），
urn:knowledge:semantics:resourceKind 区分共享 OWL 类别的应用资源种类。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, ValidationError
from rdflib import OWL, RDF, RDFS, SKOS, XSD, BNode, Graph, Literal, Namespace, URIRef
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.ontology_service import get_ontology
from app.domain.status_service import get_revision
from app.models.domain import OntologyRevision
from app.models.enums import ResourceKind
from app.schemas.ontology import OntologyExportFormat

_LANGUAGES = {"zh-CN": "zh-Hans", "en-US": "en"}
_REF = Namespace("urn:knowledge:ref:")
_SEMANTICS = Namespace("urn:knowledge:semantics:")
_SH = Namespace("http://www.w3.org/ns/shacl#")
_RDF_TYPES = {
    ResourceKind.ENTITY: OWL.Class,
    ResourceKind.ASSOC: OWL.Class,
    ResourceKind.DATATYPE_PROP: OWL.DatatypeProperty,
    ResourceKind.OBJECT_PROP: OWL.ObjectProperty,
    ResourceKind.DOMAIN: SKOS.Collection,
    ResourceKind.NAMESPACE: OWL.Ontology,
    ResourceKind.ONTOLOGY: OWL.Ontology,
}
_DATATYPES = {
    "string": XSD.string,
    "integer": XSD.integer,
    "decimal": XSD.decimal,
    "boolean": XSD.boolean,
    "date": XSD.date,
}


class _StructureRef(BaseModel):
    target_id: int
    role: str


class _OntologyMetadata(BaseModel):
    name: str
    iri: str
    label_i18n: dict[str, str] | None
    definition_i18n: dict[str, str] | None


class _Snapshot(BaseModel):
    iri: str
    kind: ResourceKind
    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    namespace: dict[str, str]
    parent_ids: list[int]
    resource_refs: list[_StructureRef]
    datatype_props: list[dict[str, object]] = Field(default_factory=list)
    object_prop: dict[str, object] | None = None


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


def _iri(value: str) -> URIRef:
    try:
        valid_scheme = bool(urlsplit(value).scheme)
    except ValueError:
        valid_scheme = False
    if not valid_scheme or re.search(r'[\s<>"{}|\\^`]', value):
        raise KGError(ErrorCode.INVALID_IRI, {"iri": value})
    return URIRef(value)


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
        set(_OntologyMetadata.model_fields) - published.metadata_snapshot.keys()
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
        metadata = _OntologyMetadata.model_validate(published.metadata_snapshot)
    except ValidationError as exc:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {
                "ontology_id": ontology_id,
                "reason": "invalid_ontology_metadata_snapshot",
            },
        ) from exc

    snapshots: dict[int, _Snapshot] = {}
    for resource_id, pinned_revision in published.resource_versions.items():
        rid = int(resource_id)
        frozen = get_revision(session, rid, pinned_revision)
        required = {"parent_ids", "resource_refs", "namespace"}
        missing = sorted(required - frozen.payload.keys())
        if missing:
            raise _violation(rid, "missing_snapshot_structure", fields=missing)
        try:
            snapshots[rid] = _Snapshot.model_validate(frozen.payload)
        except ValidationError as exc:
            raise _violation(rid, "invalid_snapshot_structure") from exc

    graph = Graph()
    graph.bind("owl", OWL)
    graph.bind("rdfs", RDFS)
    graph.bind("xsd", XSD)
    graph.bind("sh", _SH)
    graph.bind("kgref", _REF)
    graph.bind("kg", _SEMANTICS)
    ontology_iri = _iri(metadata.iri)
    graph.add((ontology_iri, RDF.type, OWL.Ontology))
    graph.add((ontology_iri, OWL.versionInfo, Literal(str(revision))))
    graph.add((ontology_iri, _SEMANTICS.name, Literal(metadata.name)))
    _add_annotations(graph, ontology_iri, metadata.label_i18n, metadata.definition_i18n)
    for rid, snapshot in snapshots.items():
        subject = _iri(snapshot.iri)
        prefix = snapshot.namespace.get("prefix")
        namespace_iri = snapshot.namespace.get("iri")
        if not prefix or not namespace_iri:
            raise _violation(rid, "missing_snapshot_namespace")
        graph.bind(prefix, _iri(namespace_iri), override=False)
        graph.add((subject, RDF.type, _RDF_TYPES[snapshot.kind]))
        graph.add((subject, _SEMANTICS.resourceKind, Literal(snapshot.kind.value)))
        graph.add((subject, RDFS.isDefinedBy, ontology_iri))
        _add_annotations(graph, subject, snapshot.label_i18n, snapshot.definition_i18n)
        for parent_id in snapshot.parent_ids:
            parent = _target(snapshots, rid, parent_id)
            if snapshot.kind not in (ResourceKind.ENTITY, ResourceKind.ASSOC) or (
                parent.kind not in (ResourceKind.ENTITY, ResourceKind.ASSOC)
            ):
                raise _violation(rid, "invalid_parent_kind", target_id=parent_id)
            graph.add((subject, RDFS.subClassOf, _iri(parent.iri)))
        _add_references(graph, rid, snapshot, snapshots)
        _add_constraints(graph, rid, snapshot, snapshots)
        if snapshot.kind == ResourceKind.DATATYPE_PROP:
            datatype = (snapshot.definition_i18n or {}).get("datatype")
            if datatype is None or datatype not in _DATATYPES:
                raise _violation(rid, "unsupported_datatype", datatype=datatype)
            graph.add((subject, RDFS.range, _DATATYPES[datatype]))

    content = graph.serialize(format=rdf_format.value)
    filename = re.sub(r"[^A-Za-z0-9_-]+", "-", metadata.name).strip("-") or "ontology"
    if rdf_format == OntologyExportFormat.TURTLE:
        return OntologyExport(content, "text/turtle", f"{filename}-r{revision}.ttl")
    return OntologyExport(
        content, "application/ld+json", f"{filename}-r{revision}.jsonld"
    )


def _add_annotations(
    graph: Graph,
    subject: URIRef,
    labels: dict[str, str] | None,
    definitions: dict[str, str] | None,
) -> None:
    for field, predicate in ((labels, RDFS.label), (definitions, RDFS.comment)):
        for language, text in (field or {}).items():
            if language in _LANGUAGES:
                graph.add(
                    (subject, predicate, Literal(text, lang=_LANGUAGES[language]))
                )


def _add_constraints(
    graph: Graph,
    resource_id: int,
    snapshot: _Snapshot,
    snapshots: dict[int, _Snapshot],
) -> None:
    subject = _iri(snapshot.iri)
    if snapshot.kind in (ResourceKind.ENTITY, ResourceKind.ASSOC):
        for detail in snapshot.datatype_props:
            prop_iri = detail.get("iri")
            if not isinstance(prop_iri, str):
                continue
            prop = _iri(prop_iri)
            _add_datatype_constraints(graph, subject, prop, detail)
    if snapshot.kind == ResourceKind.OBJECT_PROP and snapshot.object_prop:
        _add_object_constraints(graph, resource_id, subject, snapshot, snapshots)


def _add_datatype_constraints(
    graph: Graph,
    owner: URIRef,
    prop: URIRef,
    detail: dict[str, object],
) -> None:
    datatype = detail.get("datatype")
    if isinstance(datatype, str) and datatype in _DATATYPES:
        graph.add((prop, RDFS.range, _DATATYPES[datatype]))
    nullable = detail.get("nullable")
    default = detail.get("default_value")
    if isinstance(nullable, bool):
        graph.add((prop, _SEMANTICS.nullable, Literal(nullable)))
    if isinstance(default, str):
        graph.add((prop, _SEMANTICS.defaultValue, Literal(default)))

    enum_id = detail.get("enum_dict_id")
    enum_revision = detail.get("enum_dict_revision")
    enum_snapshot = detail.get("enum_dictionary")
    shape = URIRef(f"{prop}#shape")
    graph.add((owner, _SH.property, shape))
    graph.add((shape, _SH.path, prop))
    if isinstance(datatype, str) and datatype in _DATATYPES:
        graph.add((shape, _SH.datatype, _DATATYPES[datatype]))
    if nullable is False:
        graph.add((shape, _SH.minCount, Literal(1)))
    if isinstance(default, str):
        graph.add((shape, _SH.defaultValue, Literal(default)))
    if isinstance(enum_id, int) and isinstance(enum_revision, int):
        enum_iri = URIRef(f"urn:knowledge:enum:{enum_id}:r{enum_revision}")
        graph.add((prop, _SEMANTICS.enumDictionary, enum_iri))
        graph.add((enum_iri, _SEMANTICS.revision, Literal(enum_revision)))
        if isinstance(enum_snapshot, dict):
            values: list[str] = []
            for index, entry in enumerate(enum_snapshot.get("entries", [])):
                if not isinstance(entry, dict):
                    continue
                value = entry.get("value")
                if not isinstance(value, str):
                    continue
                values.append(value)
                entry_iri = URIRef(f"{enum_iri}#entry-{index}")
                graph.add((enum_iri, _SEMANTICS.entry, entry_iri))
                graph.add((entry_iri, _SEMANTICS.value, Literal(value)))
                labels = entry.get("label_i18n")
                if isinstance(labels, dict):
                    _add_annotations(graph, entry_iri, labels, None)
            if values:
                graph.add((shape, _SH.in_, _rdf_list(graph, values, str(prop))))


def _rdf_list(graph: Graph, values: list[str], stem: str) -> URIRef | BNode:
    head: URIRef | BNode = RDF.nil
    for index, value in reversed(list(enumerate(values))):
        node = URIRef(f"{stem}#enum-list-{index}")
        graph.add((node, RDF.first, Literal(value)))
        graph.add((node, RDF.rest, head))
        head = node
    return head


def _add_object_constraints(
    graph: Graph,
    resource_id: int,
    subject: URIRef,
    snapshot: _Snapshot,
    snapshots: dict[int, _Snapshot],
) -> None:
    detail = snapshot.object_prop or {}
    for key, predicate in (
        ("domain_cardinality", _SEMANTICS.domainCardinality),
        ("range_cardinality", _SEMANTICS.rangeCardinality),
        ("domain_role_i18n", _SEMANTICS.domainRole),
        ("range_role_i18n", _SEMANTICS.rangeRole),
        ("owl", _SEMANTICS.owlFeatures),
    ):
        value = detail.get(key)
        if value is not None:
            graph.add(
                (subject, predicate, Literal(json.dumps(value, ensure_ascii=False)))
            )
    owl = detail.get("owl")
    if isinstance(owl, dict):
        for feature, rdf_type in (
            ("functional", OWL.FunctionalProperty),
            ("inverse_functional", OWL.InverseFunctionalProperty),
            ("symmetric", OWL.SymmetricProperty),
            ("transitive", OWL.TransitiveProperty),
        ):
            if owl.get(feature) is True:
                graph.add((subject, RDF.type, rdf_type))

    for ref in snapshot.resource_refs:
        if ref.role not in {"relation_domain", "relation_range"}:
            continue
        target = _target(snapshots, resource_id, ref.target_id)
        target_iri = _iri(target.iri)
        cardinality = detail.get(
            "domain_cardinality"
            if ref.role == "relation_domain"
            else "range_cardinality",
            {},
        )
        if not isinstance(cardinality, dict):
            continue
        path: URIRef | BNode = subject
        if ref.role == "relation_range":
            path = URIRef(f"{subject}#inverse-range")
            graph.add((path, _SH.inversePath, subject))
        shape = URIRef(f"{target_iri}#relation-shape-{resource_id}-{ref.role}")
        graph.add((target_iri, _SH.property, shape))
        graph.add((shape, _SH.path, path))
        minimum = cardinality.get("min")
        maximum = cardinality.get("max")
        if isinstance(minimum, int):
            graph.add((shape, _SH.minCount, Literal(minimum)))
        if isinstance(maximum, int) and maximum >= 0:
            graph.add((shape, _SH.maxCount, Literal(maximum)))


def _target(
    snapshots: dict[int, _Snapshot], resource_id: int, target_id: int
) -> _Snapshot:
    target = snapshots.get(target_id)
    if target is None:
        raise _violation(
            resource_id, "incomplete_snapshot_closure", target_id=target_id
        )
    return target


def _add_references(
    graph: Graph,
    resource_id: int,
    snapshot: _Snapshot,
    snapshots: dict[int, _Snapshot],
) -> None:
    subject = _iri(snapshot.iri)
    endpoint_roles: set[str] = set()
    for ref in snapshot.resource_refs:
        target = _target(snapshots, resource_id, ref.target_id)
        target_iri = _iri(target.iri)
        if ref.role in {"relation_domain", "relation_range"}:
            if snapshot.kind != ResourceKind.OBJECT_PROP or (
                target.kind != ResourceKind.ENTITY
            ):
                raise _violation(resource_id, "invalid_endpoint_kind", role=ref.role)
            predicate = RDFS.domain if ref.role == "relation_domain" else RDFS.range
            graph.add((subject, predicate, target_iri))
            endpoint_roles.add(ref.role)
        elif ref.role in {"data_prop", "assoc_attribute"}:
            if snapshot.kind not in (ResourceKind.ENTITY, ResourceKind.ASSOC) or (
                target.kind != ResourceKind.DATATYPE_PROP
            ):
                raise _violation(resource_id, "invalid_attribute_kind", role=ref.role)
            graph.add((target_iri, RDFS.domain, subject))
        elif ref.role == "inverse_of":
            if snapshot.kind != ResourceKind.OBJECT_PROP or (
                target.kind != ResourceKind.OBJECT_PROP
            ):
                raise _violation(resource_id, "invalid_inverse_kind")
            graph.add((subject, OWL.inverseOf, target_iri))
        elif ref.role == "assoc_resource":
            if snapshot.kind != ResourceKind.OBJECT_PROP or (
                target.kind != ResourceKind.ASSOC
            ):
                raise _violation(resource_id, "invalid_association_kind")
        else:
            raise _violation(resource_id, "unsupported_reference_role", role=ref.role)
        graph.add((subject, _REF[ref.role], target_iri))
    if snapshot.kind == ResourceKind.OBJECT_PROP and endpoint_roles != {
        "relation_domain",
        "relation_range",
    }:
        raise _violation(resource_id, "missing_relation_endpoints")
