"""Strict, database-free RDF restore parsing.

Every issue blocks a complete restore. Partial resources are useful for preview only;
callers must not apply a document with issues or unsupported triples. Source enum IDs
and revisions identify the imported history, never a local database version.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, ValidationError
from rdflib import OWL, RDF, RDFS, XSD, BNode, Graph, Literal, URIRef
from rdflib.term import Node

from app.models.enums import ResourceKind
from app.schemas.enum_dictionary import EnumDictionaryInput
from app.schemas.ontology_import import ImportFormat, OntologyImportConflict
from app.schemas.type import DataTypePropCreate
from app.semantics.ontology_rdf import (
    _DATATYPES,
    _MAX_TRIPLES,
    _REF,
    OntologyRdfMetadata,
    _invalid_import,
    _parse_graph,
)
from app.semantics.ontology_rdf import (
    _SEMANTICS as KG,
)
from app.semantics.ontology_rdf import (
    _SH as SH,
)


class RestoreRef(BaseModel):
    role: str
    target_iri: str


class RestoreEnum(BaseModel):
    iri: str
    source_revision: int
    definition: EnumDictionaryInput


class RestoreResource(BaseModel):
    iri: str
    name: str
    kind: ResourceKind
    namespace_iri: str
    namespace_prefix: str
    label_i18n: dict[str, str] | None = None
    definition_i18n: dict[str, str] | None = None
    parent_iris: list[str] = Field(default_factory=list)
    refs: list[RestoreRef] = Field(default_factory=list)
    datatype: DataTypePropCreate | None = None
    enum_iri: str | None = None
    object_prop: dict[str, object] | None = None


class RestoreDocument(BaseModel):
    metadata: OntologyRdfMetadata | None = None
    source_revision: int | None = None
    resources: list[RestoreResource] = Field(default_factory=list)
    enums: list[RestoreEnum] = Field(default_factory=list)
    unsupported_triples: list[str] = Field(default_factory=list)
    issues: list[OntologyImportConflict] = Field(default_factory=list)
    triple_count: int


_KINDS = {
    OWL.Class: ResourceKind.ENTITY,
    RDFS.Class: ResourceKind.ENTITY,
    OWL.DatatypeProperty: ResourceKind.DATATYPE_PROP,
    OWL.ObjectProperty: ResourceKind.OBJECT_PROP,
}
_FEATURES = {
    "functional": OWL.FunctionalProperty,
    "inverse_functional": OWL.InverseFunctionalProperty,
    "symmetric": OWL.SymmetricProperty,
    "transitive": OWL.TransitiveProperty,
}
_LANGS = {
    "zh": "zh-CN",
    "zh-hans": "zh-CN",
    "zh-cn": "zh-CN",
    "en": "en-US",
    "en-us": "en-US",
}
_CLASSES = {ResourceKind.ENTITY, ResourceKind.ASSOC}
# Match the roles supported by the full export service. Unconsumed roles remain
# in unsupported_triples and block restore, even if the raw serializer emits them.
_ROLES = {
    "data_prop",
    "assoc_attribute",
    "relation_domain",
    "relation_range",
    "inverse_of",
    "assoc_resource",
}
_SINGLE_ROLES = {"relation_domain", "relation_range", "inverse_of", "assoc_resource"}


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _json_constant(value: str) -> object:
    raise ValueError("nonfinite_json_number")


class _Parser:
    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self.used: set[tuple[Node, Node, Node]] = set()
        self.document = RestoreDocument(triple_count=len(graph))
        self.named_triples: list[str] = []
        # JSON-LD named graphs live in the same store but are invisible when
        # iterating Graph. Preserve and block them instead of reporting success
        # after discarding their statements (or bypassing the triple limit).
        for context in graph.store.contexts():
            if not isinstance(context, Graph) or context.identifier == graph.identifier:
                continue
            if (None, OWL.imports, None) in context:
                raise _invalid_import("owl_imports_not_allowed")
            self.named_triples.extend(
                " ".join(node.n3() for node in (*triple, context.identifier)) + " ."
                for triple in context
            )
            self.issue(context.identifier, "named_graph_not_supported")
        self.document.triple_count += len(self.named_triples)
        if self.document.triple_count > _MAX_TRIPLES:
            raise _invalid_import("too_many_triples", max_triples=_MAX_TRIPLES)
        self.resources: dict[str, RestoreResource] = {}
        self.shapes: dict[tuple[str, str], Node] = {}
        self.enum_orders: dict[str, list[str]] = {}

    def issue(self, subject: Node | str, reason: str, **params: object) -> None:
        issue = OntologyImportConflict(
            iri=str(subject),
            code="INVALID_RESTORE_DATA",
            params={"reason": reason, **params},
        )
        if issue not in self.document.issues:
            self.document.issues.append(issue)

    def values(self, subject: Node, predicate: URIRef) -> list[Node]:
        values = sorted(
            self.graph.objects(subject, predicate), key=lambda node: node.n3()
        )
        self.used.update((subject, predicate, value) for value in values)
        return values

    def one(
        self, subject: Node, predicate: URIRef, *, required: bool = False
    ) -> Node | None:
        values = self.values(subject, predicate)
        if len(values) != 1:
            if values or required:
                self.issue(
                    subject,
                    "field_cardinality",
                    predicate=str(predicate),
                    count=len(values),
                )
            return None
        return values[0]

    def string(
        self, subject: Node, predicate: URIRef, *, required: bool = False
    ) -> str | None:
        value = self.one(subject, predicate, required=required)
        if value is None:
            return None
        return self.text(subject, predicate, value)

    def text(self, subject: Node, predicate: URIRef, value: Node) -> str | None:
        if (
            not isinstance(value, Literal)
            or value.language
            or value.datatype not in (None, XSD.string)
        ):
            self.issue(subject, "expected_string", predicate=str(predicate))
            return None
        return str(value)

    def iri(self, subject: Node, value: Node, predicate: URIRef) -> str | None:
        try:
            valid = isinstance(value, URIRef) and bool(urlsplit(str(value)).scheme)
        except ValueError:
            valid = False
        if not valid or re.search(r'[\s<>"{}|\\^`]', str(value)):
            self.issue(
                subject, "expected_iri", predicate=str(predicate), value=str(value)
            )
            return None
        return str(value)

    def targets(self, subject: Node, predicate: URIRef) -> list[str]:
        return [
            iri
            for value in self.values(subject, predicate)
            if (iri := self.iri(subject, value, predicate)) is not None
        ]

    def integer(
        self,
        subject: Node,
        predicate: URIRef,
        *,
        required: bool = False,
        text: bool = False,
    ) -> int | None:
        value = self.one(subject, predicate, required=required)
        if value is None:
            return None
        allowed: set[URIRef | None] = {
            XSD.integer,
            XSD.nonNegativeInteger,
            XSD.positiveInteger,
        }
        if text:
            allowed.update({None, XSD.string})
        if (
            not isinstance(value, Literal)
            or value.language
            or value.datatype not in allowed
            or not re.fullmatch(r"[+]?[0-9]+", str(value))
        ):
            self.issue(
                subject, "expected_nonnegative_integer", predicate=str(predicate)
            )
            return None
        try:
            return int(str(value))
        except ValueError:
            self.issue(subject, "integer_out_of_range", predicate=str(predicate))
            return None

    def boolean(
        self, subject: Node, predicate: URIRef, *, required: bool = False
    ) -> bool | None:
        value = self.one(subject, predicate, required=required)
        if value is None:
            return None
        if (
            not isinstance(value, Literal)
            or value.datatype != XSD.boolean
            or value.ill_typed
            or type(value.toPython()) is not bool
        ):
            self.issue(subject, "expected_boolean", predicate=str(predicate))
            return None
        return bool(value.toPython())

    def labels(self, subject: Node, predicate: URIRef) -> dict[str, str] | None:
        result: dict[str, str] = {}
        for value in self.values(subject, predicate):
            language = (
                _LANGS.get((value.language or "").lower())
                if isinstance(value, Literal)
                else None
            )
            if language is None:
                self.issue(
                    subject,
                    "unsupported_language",
                    predicate=str(predicate),
                    value=value.n3(),
                )
            elif language in result:
                self.issue(
                    subject,
                    "duplicate_language",
                    predicate=str(predicate),
                    language=language,
                )
            else:
                result[language] = str(value)
        return result or None

    def metadata(self) -> None:
        roots = sorted(set(self.graph.subjects(RDF.type, OWL.Ontology)), key=str)
        if len(roots) != 1:
            self.issue("", "ontology_root_cardinality", count=len(roots))
            return
        root = roots[0]
        if self.iri(root, root, RDF.type) is None:
            return
        self.used.add((root, RDF.type, OWL.Ontology))
        name = self.string(root, KG.name, required=True)
        revision = self.integer(root, OWL.versionInfo, required=True, text=True)
        if revision == 0:
            self.issue(root, "invalid_source_revision")
        elif revision is not None:
            self.document.source_revision = revision
        labels = self.labels(root, RDFS.label)
        definitions = self.labels(root, RDFS.comment)
        if name:
            self.document.metadata = OntologyRdfMetadata(
                name=name, iri=str(root), label_i18n=labels, definition_i18n=definitions
            )
        elif name is not None:
            self.issue(root, "empty_name")

    def resource_headers(self) -> None:
        subjects = set(self.graph.subjects(KG.resourceKind, None)) | set(
            self.graph.subjects(RDFS.isDefinedBy, None)
        )
        for candidate_type in _KINDS:
            subjects.update(self.graph.subjects(RDF.type, candidate_type))
        for subject in sorted(subjects, key=str):
            if self.iri(subject, subject, RDF.type) is None:
                continue
            types = set(self.graph.objects(subject, RDF.type))
            base_types = {item for item in _KINDS if item in types}
            explicit = self.string(subject, KG.resourceKind)
            if len(base_types) != 1:
                self.issue(
                    subject,
                    "resource_type_cardinality",
                    types=sorted(map(str, base_types)),
                )
                continue
            rdf_type = next(iter(base_types))
            kind = _KINDS[rdf_type]
            if explicit is not None:
                try:
                    kind = ResourceKind(explicit)
                except ValueError:
                    self.issue(subject, "unsupported_resource_kind", kind=explicit)
                    continue
                expected = ResourceKind.ENTITY if kind == ResourceKind.ASSOC else kind
                if expected != _KINDS[rdf_type]:
                    self.issue(subject, "conflicting_resource_kind", kind=explicit)
                    continue
            self.used.add((subject, RDF.type, rdf_type))
            name = self.string(subject, KG.name)
            namespace = self.string(subject, KG.namespace)
            prefix = self.string(subject, KG.namespacePrefix)
            if self.document.metadata and (
                name is None or namespace is None or prefix is None
            ):
                self.issue(subject, "missing_resource_metadata")
            fallback_namespace, _, local = str(subject).rpartition(
                "#" if "#" in str(subject) else "/"
            )
            fallback_namespace += "#" if "#" in str(subject) else "/"
            if namespace is None:
                namespace = fallback_namespace
            if prefix is None:
                prefixes = sorted(
                    str(key)
                    for key, value in self.graph.namespaces()
                    if str(value) == namespace
                )
                prefix = prefixes[0] if len(prefixes) == 1 else ""
            if (
                not namespace
                or self.iri(subject, URIRef(namespace), KG.namespace) is None
            ):
                self.issue(subject, "invalid_namespace")
            if not name and name is not None:
                self.issue(subject, "empty_name")
            defined_by = self.targets(subject, RDFS.isDefinedBy)
            if self.document.metadata and defined_by != [self.document.metadata.iri]:
                self.issue(subject, "ontology_membership", targets=defined_by)
            elif not self.document.metadata and defined_by:
                self.issue(
                    subject, "unresolved_ontology_membership", targets=defined_by
                )
            self.resources[str(subject)] = RestoreResource(
                iri=str(subject),
                name=name if name is not None else local,
                kind=kind,
                namespace_iri=namespace,
                namespace_prefix=prefix,
                label_i18n=self.labels(subject, RDFS.label),
                definition_i18n=self.labels(subject, RDFS.comment),
                parent_iris=self.targets(subject, RDFS.subClassOf),
            )

    def add_ref(self, resource: RestoreResource, role: str, target: str) -> None:
        ref = RestoreRef(role=role, target_iri=target)
        if ref not in resource.refs:
            resource.refs.append(ref)

    def references(self) -> None:
        for resource in self.resources.values():
            subject = URIRef(resource.iri)
            for role in sorted(_ROLES):
                for target in self.targets(subject, _REF[role]):
                    self.add_ref(resource, role, target)
        for resource in self.resources.values():
            subject = URIRef(resource.iri)
            if resource.kind == ResourceKind.OBJECT_PROP:
                for predicate, role in (
                    (RDFS.domain, "relation_domain"),
                    (RDFS.range, "relation_range"),
                    (OWL.inverseOf, "inverse_of"),
                ):
                    standard = self.targets(subject, predicate)
                    explicit = [
                        ref.target_iri for ref in resource.refs if ref.role == role
                    ]
                    if standard and explicit and set(standard) != set(explicit):
                        self.issue(subject, "conflicting_reference", role=role)
                    for target in standard:
                        self.add_ref(resource, role, target)
            elif resource.kind == ResourceKind.DATATYPE_PROP:
                owners = self.targets(subject, RDFS.domain)
                explicit_owners = [
                    item.iri
                    for item in self.resources.values()
                    for ref in item.refs
                    if ref.role in {"data_prop", "assoc_attribute"}
                    and ref.target_iri == resource.iri
                ]
                if owners and explicit_owners and set(owners) != set(explicit_owners):
                    self.issue(subject, "conflicting_property_owner")
                for owner in owners:
                    item = self.resources.get(owner)
                    if item is None:
                        self.issue(subject, "incomplete_resource_closure", target=owner)
                    else:
                        role = (
                            "assoc_attribute"
                            if item.kind == ResourceKind.ASSOC
                            else "data_prop"
                        )
                        self.add_ref(item, role, resource.iri)

        # Ordinary RDF has no snapshot name/namespace fields. Only infer an
        # attribute name when its unique owner and canonical path prove it.
        for resource in self.resources.values():
            subject = URIRef(resource.iri)
            if (
                resource.kind != ResourceKind.DATATYPE_PROP
                or (subject, KG.name, None) in self.graph
            ):
                continue
            inferred_owners = [
                item
                for item in self.resources.values()
                for ref in item.refs
                if ref.role in {"data_prop", "assoc_attribute"}
                and ref.target_iri == resource.iri
            ]
            if len(inferred_owners) == 1 and resource.iri.startswith(
                f"{inferred_owners[0].iri}/"
            ):
                inferred_owner = inferred_owners[0]
                local_name = resource.iri[len(inferred_owner.iri) + 1 :]
                resource.name = f"{inferred_owner.name}.{local_name}"
                if (subject, KG.namespace, None) not in self.graph:
                    resource.namespace_iri = inferred_owner.namespace_iri
                if (subject, KG.namespacePrefix, None) not in self.graph:
                    resource.namespace_prefix = inferred_owner.namespace_prefix

    def shape_index(self) -> None:
        for owner, shape in sorted(
            self.graph.subject_objects(SH.property),
            key=lambda pair: tuple(map(str, pair)),
        ):
            owner_resource = self.resources.get(str(owner))
            if (
                owner_resource is None
                or owner_resource.kind not in _CLASSES
                or not isinstance(shape, (URIRef, BNode))
            ):
                self.issue(owner, "invalid_shape_owner")
                continue
            self.used.add((owner, SH.property, shape))
            path = self.one(shape, SH.path, required=True)
            if path is None:
                continue
            inverse = (
                self.one(path, SH.inversePath)
                if isinstance(path, (URIRef, BNode))
                else None
            )
            target = inverse if inverse is not None else path
            iri = self.iri(shape, target, SH.path)
            resource = self.resources.get(iri or "")
            if resource is None or resource.kind not in {
                ResourceKind.DATATYPE_PROP,
                ResourceKind.OBJECT_PROP,
            }:
                self.issue(shape, "unresolved_shape_path", path=str(target))
                continue
            role = "range" if inverse is not None else "domain"
            if resource.kind == ResourceKind.DATATYPE_PROP:
                if inverse is not None:
                    self.issue(shape, "inverse_datatype_path")
                    continue
                refs = [
                    ref
                    for ref in owner_resource.refs
                    if ref.role in {"data_prop", "assoc_attribute"}
                    and ref.target_iri == iri
                ]
                if not refs:
                    self.issue(shape, "shape_owner_mismatch")
                role = "datatype"
            elif not any(
                ref.role == f"relation_{role}" and ref.target_iri == str(owner)
                for ref in resource.refs
            ):
                self.issue(shape, "shape_endpoint_mismatch", role=role)
            key = (resource.iri, role)
            if key in self.shapes:
                self.issue(resource.iri, "duplicate_property_shape", role=role)
            else:
                self.shapes[key] = shape
            if (shape, RDF.type, SH.PropertyShape) in self.graph:
                self.used.add((shape, RDF.type, SH.PropertyShape))

    def rdf_list(self, shape: Node) -> list[str] | None:
        head = self.one(shape, SH["in"])
        if head is None:
            return None
        values: list[str] = []
        seen: set[Node] = set()
        while head != RDF.nil:
            if head in seen or not isinstance(head, (URIRef, BNode)):
                self.issue(shape, "invalid_enum_list")
                return None
            seen.add(head)
            value = self.string(head, RDF.first, required=True)
            tail = self.one(head, RDF.rest, required=True)
            if value is None or tail is None:
                return None
            values.append(value)
            head = tail
        if not values or len(set(values)) != len(values):
            self.issue(shape, "empty_or_duplicate_enum_list")
        return values

    def enum(
        self, subject: URIRef, enum_iri: str, values: list[str] | None
    ) -> tuple[int | None, int | None]:
        node = URIRef(enum_iri)
        revision = self.integer(node, KG.revision, required=True)
        enum_id: int | None = None
        source = re.fullmatch(
            r"urn:knowledge:enum:([1-9][0-9]*):r([1-9][0-9]*)", enum_iri
        )
        if source:
            try:
                enum_id = int(source[1])
                if revision != int(source[2]):
                    self.issue(node, "enum_revision_mismatch")
            except ValueError:
                self.issue(
                    node, "integer_out_of_range", predicate=str(KG.enumDictionary)
                )
        if revision == 0:
            self.issue(node, "invalid_source_revision")
            revision = None
        name = self.string(node, KG.name, required=True)
        labels = self.labels(node, RDFS.label)
        definitions = self.labels(node, RDFS.comment)
        entries: dict[str, dict[str, object]] = {}
        for entry in self.values(node, KG.entry):
            if not isinstance(entry, (URIRef, BNode)):
                self.issue(node, "invalid_enum_entry")
                continue
            value = self.string(entry, KG.value, required=True)
            entry_labels = self.labels(entry, RDFS.label)
            if value in entries:
                self.issue(node, "duplicate_enum_value", value=value)
            elif value is not None:
                entries[value] = {"value": value, "label_i18n": entry_labels}
        if values is None or set(values) != set(entries):
            self.issue(subject, "enum_list_mismatch", enum_iri=enum_iri)
        elif enum_iri in self.enum_orders and self.enum_orders[enum_iri] != values:
            self.issue(node, "conflicting_enum_order")
        else:
            self.enum_orders[enum_iri] = values
        raw_definition = {
            "name": name,
            "label_i18n": labels,
            "definition_i18n": definitions,
            "entries": [entries[value] for value in values or [] if value in entries],
        }
        try:
            definition = EnumDictionaryInput.model_validate(raw_definition)
        except ValidationError:
            self.issue(node, "invalid_or_missing_enum_definition")
        else:
            if definition.model_dump() != raw_definition:
                self.issue(node, "enum_definition_normalization")
                return enum_id, revision
            if revision is not None and not any(
                item.iri == enum_iri for item in self.document.enums
            ):
                self.document.enums.append(
                    RestoreEnum(
                        iri=enum_iri, source_revision=revision, definition=definition
                    )
                )
        return enum_id, revision

    def decimal(self, shape: Node, predicate: URIRef) -> str | None:
        value = self.one(shape, predicate)
        if value is None:
            return None
        try:
            if not isinstance(value, Literal) or value.datatype not in {
                XSD.decimal,
                XSD.integer,
            }:
                raise InvalidOperation
            number = Decimal(str(value))
            if not number.is_finite():
                raise InvalidOperation
        except InvalidOperation:
            self.issue(shape, "invalid_numeric_bound", predicate=str(predicate))
            return None
        return str(value)

    def datatype(self, resource: RestoreResource) -> None:
        subject = URIRef(resource.iri)
        property_name = self.string(subject, KG.propertyName)
        if property_name is not None and not property_name.strip():
            self.issue(subject, "empty_property_name")
        shape = self.shapes.get((resource.iri, "datatype"))
        datatype_node = self.one(subject, RDFS.range)
        shaped_datatype = self.one(shape, SH.datatype) if shape is not None else None
        if (
            datatype_node is not None
            and shaped_datatype is not None
            and datatype_node != shaped_datatype
        ):
            self.issue(subject, "conflicting_datatype")
        datatype_node = datatype_node if datatype_node is not None else shaped_datatype
        enum_node = self.one(subject, KG.enumDictionary)
        values = self.rdf_list(shape) if shape is not None else None
        datatype = next(
            (name for name, iri in _DATATYPES.items() if iri == datatype_node), None
        )
        enum_id: int | None = None
        enum_revision: int | None = None
        if enum_node is not None:
            resource.enum_iri = self.iri(subject, enum_node, KG.enumDictionary)
            if resource.enum_iri is not None:
                enum_id, enum_revision = self.enum(subject, resource.enum_iri, values)
            if datatype_node is not None:
                self.issue(subject, "conflicting_enum_datatype")
            datatype = "enum"
        elif values is not None:
            self.issue(subject, "missing_enum_dictionary")
        native = (subject, KG.resourceKind, None) in self.graph
        nullable = self.boolean(subject, KG.nullable, required=native)
        recorded = self.boolean(subject, KG.constraintsRecorded, required=native)
        if recorded is False:
            self.issue(subject, "incomplete_constraint_snapshot")
        default = self.string(subject, KG.defaultValue)
        source_clause = self.string(subject, KG.sourceClauseRef)
        minimum = maximum = None
        lower = upper = None
        if shape is not None:
            minimum = self.integer(shape, SH.minCount)
            maximum = self.integer(shape, SH.maxCount)
            lower = self.decimal(shape, SH.minInclusive)
            upper = self.decimal(shape, SH.maxInclusive)
            shape_default = self.string(shape, SH.defaultValue)
            if (
                default is not None
                and shape_default is not None
                and default != shape_default
            ):
                self.issue(subject, "conflicting_default")
            if default is None:
                default = shape_default
        elif (subject, KG.resourceKind, None) in self.graph:
            self.issue(subject, "missing_datatype_shape")
        if datatype is None:
            self.issue(subject, "unsupported_or_missing_datatype")
            return
        if nullable is False and (minimum or 0) < 1:
            self.issue(subject, "nullable_cardinality_mismatch")
        if minimum is not None and maximum is not None and minimum > maximum:
            self.issue(subject, "invalid_cardinality_bounds")
        if (lower is not None or upper is not None) and datatype not in {
            "integer",
            "decimal",
        }:
            self.issue(subject, "numeric_bound_datatype_mismatch")
        if lower is not None and upper is not None and Decimal(lower) > Decimal(upper):
            self.issue(subject, "invalid_numeric_bounds")
        if (
            datatype == "enum"
            and default is not None
            and values is not None
            and default not in values
        ):
            self.issue(subject, "enum_default_not_in_list")
        resource.datatype = DataTypePropCreate(
            name=property_name
            if property_name is not None
            else resource.name.rsplit(".", 1)[-1],
            label_i18n=resource.label_i18n,
            definition_i18n=resource.definition_i18n,
            datatype=datatype,
            enum_dict_id=enum_id,
            enum_dict_revision=enum_revision,
            nullable=nullable if nullable is not None else not bool(minimum),
            default_value=default,
            min_cardinality=minimum,
            max_cardinality=maximum,
            min_value=lower,
            max_value=upper,
            source_clause_ref=source_clause,
        )

    def json_field(
        self, subject: URIRef, predicate: URIRef
    ) -> dict[str, object] | None:
        text = self.string(subject, predicate)
        if text is None:
            return None
        try:
            value = json.loads(
                text, object_pairs_hook=_json_object, parse_constant=_json_constant
            )
            if not isinstance(value, dict):
                raise ValueError("expected_object")
        except (ValueError, RecursionError):
            self.issue(subject, "invalid_json_object", predicate=str(predicate))
            return None
        return value

    def json_labels(self, subject: URIRef, value: object, field: str) -> bool:
        if value is None:
            return True
        if (
            not isinstance(value, dict)
            or set(value) - {"zh-CN", "en-US"}
            or any(not isinstance(text, str) for text in value.values())
        ):
            self.issue(subject, "invalid_json_labels", field=field)
            return False
        return True

    def object_property(self, resource: RestoreResource) -> None:
        subject = URIRef(resource.iri)
        detail: dict[str, object] = {}
        for side, predicate in (
            ("domain", KG.domainCardinality),
            ("range", KG.rangeCardinality),
        ):
            cardinality = self.json_field(subject, predicate)
            shape = self.shapes.get((resource.iri, side))
            minimum = self.integer(shape, SH.minCount) if shape is not None else None
            maximum = self.integer(shape, SH.maxCount) if shape is not None else None
            if cardinality is not None:
                lower, upper = cardinality.get("min"), cardinality.get("max")
                if (
                    set(cardinality) - {"min", "max", "role_label_i18n"}
                    or type(lower) is not int
                    or type(upper) is not int
                    or lower < 0
                    or upper < -1
                    or (upper != -1 and upper < lower)
                ):
                    self.issue(subject, "invalid_json_cardinality", side=side)
                else:
                    if (
                        shape is None
                        or minimum != lower
                        or maximum != (None if upper == -1 else upper)
                    ):
                        self.issue(subject, "cardinality_shape_mismatch", side=side)
                    detail[f"{side}_cardinality"] = cardinality
                self.json_labels(
                    subject, cardinality.get("role_label_i18n"), f"{side}_cardinality"
                )
            else:
                if minimum is not None and maximum is not None and minimum > maximum:
                    self.issue(subject, "invalid_cardinality_bounds", side=side)
                detail[f"{side}_cardinality"] = {
                    "min": minimum or 0,
                    "max": maximum if maximum is not None else -1,
                }
            role = self.json_field(
                subject, KG.domainRole if side == "domain" else KG.rangeRole
            )
            if self.json_labels(subject, role, f"{side}_role_i18n"):
                detail[f"{side}_role_i18n"] = role
        owl = self.json_field(subject, KG.owlFeatures)
        if owl is not None and (
            set(owl) - _FEATURES.keys()
            or any(type(value) is not bool for value in owl.values())
        ):
            self.issue(subject, "invalid_owl_features")
        features: dict[str, bool] = {}
        for key, rdf_type in _FEATURES.items():
            enabled = (subject, RDF.type, rdf_type) in self.graph
            if enabled:
                self.used.add((subject, RDF.type, rdf_type))
            if owl is not None and owl.get(key, False) != enabled:
                self.issue(subject, "owl_feature_mismatch", feature=key)
            features[key] = enabled
        detail["owl"] = features
        resource.object_prop = detail

    def closure(self) -> None:
        names: dict[str, str] = {}
        prefixes: dict[str, str] = {}
        for resource in self.resources.values():
            if resource.name in names and names[resource.name] != resource.iri:
                self.issue(resource.iri, "duplicate_resource_name", name=resource.name)
            names[resource.name] = resource.iri
            prefix = resource.namespace_prefix
            if prefix in prefixes and prefixes[prefix] != resource.namespace_iri:
                self.issue(resource.iri, "conflicting_namespace_prefix", prefix=prefix)
            prefixes[prefix] = resource.namespace_iri
            for parent in resource.parent_iris:
                target = self.resources.get(parent)
                if target is None:
                    self.issue(
                        resource.iri, "incomplete_resource_closure", target=parent
                    )
                elif resource.kind not in _CLASSES or target.kind not in _CLASSES:
                    self.issue(resource.iri, "invalid_parent_kind", target=parent)
            for role in _SINGLE_ROLES:
                count = sum(ref.role == role for ref in resource.refs)
                required = resource.kind == ResourceKind.OBJECT_PROP and role in {
                    "relation_domain",
                    "relation_range",
                }
                if count > 1 or (required and count != 1):
                    self.issue(
                        resource.iri, "reference_cardinality", role=role, count=count
                    )
            for ref in resource.refs:
                target = self.resources.get(ref.target_iri)
                if target is None:
                    self.issue(
                        resource.iri,
                        "incomplete_resource_closure",
                        target=ref.target_iri,
                    )
                    continue
                if ref.role in {"data_prop", "assoc_attribute"}:
                    valid = (
                        resource.kind in _CLASSES
                        and target.kind == ResourceKind.DATATYPE_PROP
                    )
                else:
                    target_kind = (
                        ResourceKind.ENTITY
                        if ref.role in {"relation_domain", "relation_range"}
                        else ResourceKind.ASSOC
                        if ref.role == "assoc_resource"
                        else ResourceKind.OBJECT_PROP
                    )
                    valid = (
                        resource.kind == ResourceKind.OBJECT_PROP
                        and target.kind == target_kind
                    )
                if not valid:
                    self.issue(
                        resource.iri,
                        "invalid_reference_kind",
                        role=ref.role,
                        target=ref.target_iri,
                    )
            if resource.kind == ResourceKind.DATATYPE_PROP:
                owners = [
                    item
                    for item in self.resources.values()
                    for ref in item.refs
                    if ref.role in {"data_prop", "assoc_attribute"}
                    and ref.target_iri == resource.iri
                ]
                if len(owners) != 1:
                    self.issue(
                        resource.iri, "property_owner_cardinality", count=len(owners)
                    )
                else:
                    owner = owners[0]
                    prop_name = (
                        resource.datatype.name
                        if resource.datatype is not None
                        else resource.name.removeprefix(f"{owner.name}.")
                    )
                    if (
                        resource.name.startswith(f"{owner.name}.")
                        and resource.name != f"{owner.name}.{prop_name}"
                    ):
                        self.issue(resource.iri, "conflicting_property_name")
                    if (
                        resource.iri != f"{owner.iri}/{prop_name}"
                        or resource.namespace_iri != owner.namespace_iri
                    ):
                        self.issue(
                            resource.iri, "property_iri_mismatch", owner=owner.iri
                        )
            elif resource.iri != resource.namespace_iri + resource.name:
                self.issue(resource.iri, "resource_iri_mismatch")
            resource.refs.sort(key=lambda ref: (ref.role, ref.target_iri))
        # Iterative traversal is bounded by the input triple limit, including cycles.
        for start in self.resources.values():
            pending = list(start.parent_iris)
            seen: set[str] = set()
            while pending:
                parent = pending.pop()
                if parent == start.iri:
                    self.issue(start.iri, "cyclic_parent_hierarchy")
                    break
                if parent not in seen and parent in self.resources:
                    seen.add(parent)
                    pending.extend(self.resources[parent].parent_iris)

    def parse(self) -> RestoreDocument:
        self.metadata()
        self.resource_headers()
        self.references()
        self.shape_index()
        for resource in self.resources.values():
            if resource.kind == ResourceKind.DATATYPE_PROP:
                self.datatype(resource)
            elif resource.kind == ResourceKind.OBJECT_PROP:
                self.object_property(resource)
        self.closure()
        self.document.resources = list(self.resources.values())
        self.document.enums.sort(key=lambda item: item.iri)
        self.document.unsupported_triples = sorted(
            self.named_triples
            + [
                " ".join(node.n3() for node in triple) + " ."
                for triple in self.graph
                if triple not in self.used
            ]
        )
        if self.document.unsupported_triples:
            self.document.issues.append(
                OntologyImportConflict(
                    iri="",
                    code="UNSUPPORTED_TRIPLES",
                    params={"count": len(self.document.unsupported_triples)},
                )
            )
        return self.document


def parse_restore_document(format: ImportFormat, content: str) -> RestoreDocument:  # noqa: A002
    """Parse the supported subset without network, database access or mutation.

    Syntax, external context/import and size errors use the existing RDF adapter's
    KGError contract. Semantic loss and ambiguity are returned as blocking issues.
    """
    if format not in {"turtle", "json-ld"}:
        raise _invalid_import("unsupported_import_format", format=format)
    return _Parser(_parse_graph(format, content)).parse()
