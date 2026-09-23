"""本体 RDF 适配：解析文本、构图和序列化，不查询数据库或选择资源版本。

urn:knowledge:ref:{role} 保留引用角色，resourceKind 区分实体与关联实体。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from pydantic import BaseModel, Field
from rdflib import OWL, RDF, RDFS, SKOS, XSD, BNode, Graph, Literal, Namespace, URIRef

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.enums import ResourceKind
from app.schemas.ontology import OntologyExportFormat
from app.schemas.ontology_import import ImportFormat, ImportResourcePreview

_MAX_BYTES = 64 * 1024
_MAX_TRIPLES = 2_000
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
_KIND_BY_RDF_TYPE = {
    OWL.Class: ResourceKind.ENTITY,
    OWL.DatatypeProperty: ResourceKind.DATATYPE_PROP,
    OWL.ObjectProperty: ResourceKind.OBJECT_PROP,
    SKOS.Collection: ResourceKind.DOMAIN,
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


class OntologyRdfMetadata(BaseModel):
    name: str
    iri: str
    label_i18n: dict[str, str] | None
    definition_i18n: dict[str, str] | None


class OntologyRdfResource(BaseModel):
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
class ParsedOntologyRdf:
    root_iri: str | None
    triple_count: int
    resources: list[ImportResourcePreview]


def _invalid_import(reason: str, **params: object) -> KGError:
    return KGError(ErrorCode.VALIDATION_VIOLATION, {"reason": reason, **params})


def _validate_jsonld_context(content: str) -> None:
    try:
        document = json.loads(content)
    except json.JSONDecodeError as exc:
        raise _invalid_import("invalid_json_ld") from exc

    def inspect_context(value: object, is_context: bool = False) -> None:
        if is_context and isinstance(value, str):
            raise _invalid_import("external_json_ld_context")
        if isinstance(value, list):
            for item in value:
                inspect_context(item, is_context)
        elif isinstance(value, dict):
            for key, item in value.items():
                inspect_context(item, key in {"@context", "@import"})

    inspect_context(document)


def _parse_graph(rdf_format: ImportFormat, content: str) -> Graph:
    if len(content.encode("utf-8")) > _MAX_BYTES:
        raise _invalid_import("import_too_large", max_bytes=_MAX_BYTES)
    if rdf_format == OntologyExportFormat.JSON_LD.value:
        _validate_jsonld_context(content)
    graph = Graph()
    try:
        graph.parse(data=content, format=rdf_format)
    except Exception as exc:
        raise _invalid_import("invalid_rdf", format=rdf_format) from exc
    if len(graph) > _MAX_TRIPLES:
        raise _invalid_import("too_many_triples", max_triples=_MAX_TRIPLES)
    if (None, OWL.imports, None) in graph:
        raise _invalid_import("owl_imports_not_allowed")
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
    value = next(iter(graph.objects(subject, _SEMANTICS.resourceKind)), None)
    if value is not None:
        try:
            return ResourceKind(str(value))
        except ValueError:
            return None
    for rdf_type, kind in _KIND_BY_RDF_TYPE.items():
        if (subject, RDF.type, rdf_type) in graph:
            return kind
    return None


def parse_ontology_rdf(rdf_format: ImportFormat, content: str) -> ParsedOntologyRdf:
    graph = _parse_graph(rdf_format, content)
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
    return ParsedOntologyRdf(root_iri, len(graph), resources)


def _iri(value: str) -> URIRef:
    try:
        valid_scheme = bool(urlsplit(value).scheme)
    except ValueError:
        valid_scheme = False
    if not valid_scheme or re.search(r'[\s<>"{}|\\^`]', value):
        raise KGError(ErrorCode.INVALID_IRI, {"iri": value})
    return URIRef(value)


def serialize_ontology_rdf(
    metadata: OntologyRdfMetadata,
    snapshots: dict[int, OntologyRdfResource],
    *,
    revision: int,
    rdf_format: OntologyExportFormat,
) -> str:
    """将已校验引用闭包与资源种类的快照转换为 RDF。"""
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
        graph.bind(
            snapshot.namespace["prefix"],
            _iri(snapshot.namespace["iri"]),
            override=False,
        )
        graph.add((subject, RDF.type, _RDF_TYPES[snapshot.kind]))
        graph.add((subject, _SEMANTICS.resourceKind, Literal(snapshot.kind.value)))
        graph.add((subject, RDFS.isDefinedBy, ontology_iri))
        _add_annotations(graph, subject, snapshot.label_i18n, snapshot.definition_i18n)
        for parent_id in snapshot.parent_ids:
            graph.add((subject, RDFS.subClassOf, _iri(snapshots[parent_id].iri)))
        _add_references(graph, snapshot, snapshots)
        _add_constraints(graph, rid, snapshot, snapshots)
        if snapshot.kind == ResourceKind.DATATYPE_PROP:
            datatype = (snapshot.definition_i18n or {}).get("datatype")
            if datatype is None or datatype not in _DATATYPES:
                raise KGError(
                    ErrorCode.VALIDATION_VIOLATION,
                    {
                        "resource_id": rid,
                        "reason": "unsupported_datatype",
                        "datatype": datatype,
                    },
                )
            graph.add((subject, RDFS.range, _DATATYPES[datatype]))
    return graph.serialize(format=rdf_format.value)


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


def _add_references(
    graph: Graph,
    snapshot: OntologyRdfResource,
    snapshots: dict[int, OntologyRdfResource],
) -> None:
    subject = _iri(snapshot.iri)
    for ref in snapshot.resource_refs:
        target_iri = _iri(snapshots[ref.target_id].iri)
        if ref.role in {"relation_domain", "relation_range"}:
            predicate = RDFS.domain if ref.role == "relation_domain" else RDFS.range
            graph.add((subject, predicate, target_iri))
        elif ref.role in {"data_prop", "assoc_attribute"}:
            graph.add((target_iri, RDFS.domain, subject))
        elif ref.role == "inverse_of":
            graph.add((subject, OWL.inverseOf, target_iri))
        graph.add((subject, _REF[ref.role], target_iri))


def _add_constraints(
    graph: Graph,
    resource_id: int,
    snapshot: OntologyRdfResource,
    snapshots: dict[int, OntologyRdfResource],
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
                graph.add((shape, _SH["in"], _rdf_list(graph, values, str(prop))))


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
    snapshot: OntologyRdfResource,
    snapshots: dict[int, OntologyRdfResource],
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
        target_iri = _iri(snapshots[ref.target_id].iri)
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
