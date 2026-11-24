"""Offline compilation of frozen rule expressions, separate from their annotations.

The OWL subset is named class/property axioms supported by OWL RL, not full DL:
subClassOf, equivalentClass, disjointWith, subPropertyOf, equivalentProperty,
inverseOf, domain/range and the four existing object-property characteristics.
Restrictions, lists, property chains, ABox statements and imports are rejected.
SHACL uses the saved-rule Core allowlist (no SPARQL/JS/custom validators).
All resource operands must belong to the supplied frozen closure. Shape subjects
are isolated on compilation so rules cannot overwrite each other or asset shapes.
Unsupported executable rules raise KGError; callers must retain NOT_RUN on failure.
DATA/DERIVATION and legacy annotations are not interpreted by this compiler.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from rdflib import OWL, RDF, RDFS, SH, XSD, BNode, Graph, Literal, URIRef

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.enums import ResourceKind
from app.semantics.rule_examples import (
    MAX_TEXT_BYTES,
    MAX_TRIPLES,
    _check_shapes,
    _parse,
)

_CLASSES = {ResourceKind.ENTITY, ResourceKind.ASSOC}
_PROPERTIES = {ResourceKind.OBJECT_PROP, ResourceKind.DATATYPE_PROP}
_CLASS_AXIOMS = {RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith}
_PROPERTY_AXIOMS = {RDFS.subPropertyOf, OWL.equivalentProperty}
_CHARACTERISTICS = {
    OWL.FunctionalProperty,
    OWL.InverseFunctionalProperty,
    OWL.SymmetricProperty,
    OWL.TransitiveProperty,
}
_DECLARATIONS = {
    OWL.Class: _CLASSES,
    OWL.ObjectProperty: {ResourceKind.OBJECT_PROP},
    OWL.DatatypeProperty: {ResourceKind.DATATYPE_PROP},
    **{feature: {ResourceKind.OBJECT_PROP} for feature in _CHARACTERISTICS},
}
_DATATYPES = {XSD.string, XSD.integer, XSD.decimal, XSD.boolean, XSD.date, XSD.anyURI}
_KG = "urn:knowledge:semantics:"


@dataclass(frozen=True)
class CompiledOntologyRules:
    tbox: Graph
    shapes: Graph


def _invalid(reason: str, rule: dict[str, object]) -> KGError:
    return KGError(
        ErrorCode.VALIDATION_VIOLATION,
        {"reason": reason, "rule_identifier": rule.get("identifier")},
    )


def _rule_payload(record: dict[str, object]) -> dict[str, object]:
    """Published/working contexts wrap RuleOut with its pinned ID and revision."""
    if "rule_id" not in record and "snapshot" not in record:
        return record
    snapshot = record.get("snapshot")
    if not isinstance(snapshot, dict):
        raise _invalid("missing_rule_snapshot", record)
    rule_id, revision = record.get("rule_id"), record.get("revision")
    snapshot_id, snapshot_revision = snapshot.get("id"), snapshot.get("revision")
    if (
        type(rule_id) is not int
        or type(revision) is not int
        or type(snapshot_id) is not int
        or type(snapshot_revision) is not int
        or snapshot_id != rule_id
        or snapshot_revision != revision
        or revision < 1
        or rule_id < 1
        or (
            "identifier" in record
            and record["identifier"] != snapshot.get("identifier")
        )
    ):
        raise _invalid("mismatched_rule_snapshot", record)
    language = snapshot.get("language")
    if not isinstance(language, str) or language not in {
        "OWL",
        "SHACL",
        "DATA",
        "DERIVATION",
    }:
        raise _invalid("unsupported_rule_language", record)
    return snapshot


def _compile_owl(
    graph: Graph, target: str, kinds: dict[str, ResourceKind], rule: dict[str, object]
) -> Graph:
    if not graph:
        raise _invalid("empty_owl_rule", rule)
    target_has_axiom = False
    for subject, predicate, obj in graph:
        if not isinstance(subject, URIRef) or str(subject) not in kinds:
            raise _invalid("owl_resource_not_frozen", rule)
        kind = kinds[str(subject)]
        if predicate == RDF.type:
            if (
                not isinstance(obj, URIRef)
                or obj not in _DECLARATIONS
                or kind not in _DECLARATIONS[obj]
            ):
                raise _invalid("unsupported_owl_declaration", rule)
            target_has_axiom |= str(subject) == target and obj in _CHARACTERISTICS
            continue
        if not isinstance(obj, URIRef):
            raise _invalid("unsupported_owl_construct", rule)
        other = kinds.get(str(obj))
        if predicate in _CLASS_AXIOMS:
            valid = kind in _CLASSES and other in _CLASSES
        elif predicate in _PROPERTY_AXIOMS:
            valid = kind in _PROPERTIES and other == kind
        elif predicate == OWL.inverseOf:
            valid = kind == other == ResourceKind.OBJECT_PROP
        elif predicate == RDFS.domain:
            valid = kind in _PROPERTIES and other in _CLASSES
        elif predicate == RDFS.range:
            valid = (kind == ResourceKind.OBJECT_PROP and other in _CLASSES) or (
                kind == ResourceKind.DATATYPE_PROP and obj in _DATATYPES
            )
        else:
            raise _invalid("unsupported_owl_construct", rule)
        if not valid:
            raise _invalid("invalid_owl_operand", rule)
        target_has_axiom |= str(subject) == target
    if not target_has_axiom:
        raise _invalid("owl_target_axiom_required", rule)
    return graph


def _compile_shapes(
    graph: Graph, target: str, kinds: dict[str, ResourceKind], rule: dict[str, object]
) -> Graph:
    if kinds[target] not in _CLASSES:
        raise _invalid("shacl_class_target_required", rule)
    _check_shapes(graph, target)
    subjects = set(graph.subjects())
    if any(str(subject) in kinds for subject in subjects):
        raise _invalid("shape_asset_collision", rule)
    for _, predicate, obj in graph:
        if predicate in {SH.targetClass, SH["class"]}:
            if not isinstance(obj, URIRef) or kinds.get(str(obj)) not in _CLASSES:
                raise _invalid("shacl_class_not_frozen", rule)
        elif predicate in {
            SH.path,
            SH.inversePath,
            SH.equals,
            SH.disjoint,
            SH.lessThan,
            SH.lessThanOrEquals,
        } and isinstance(obj, URIRef):
            if kinds.get(str(obj)) not in _PROPERTIES:
                raise _invalid("shacl_property_not_frozen", rule)
        elif predicate == SH.datatype and obj not in _DATATYPES:
            raise _invalid("unsupported_shacl_datatype", rule)
        if isinstance(obj, URIRef) and not (
            str(obj) in kinds
            or obj in subjects
            or str(obj).startswith((str(SH), str(RDF), str(RDFS)))
            or obj in _DATATYPES
        ):
            raise _invalid("shacl_reference_not_frozen", rule)
    severity = {"INFO": SH.Info, "WARNING": SH.Warning, "VIOLATION": SH.Violation}
    expected = severity.get(str(rule.get("severity", "VIOLATION")))
    if expected is None or any(
        value != expected for value in graph.objects(None, SH.severity)
    ):
        raise _invalid("severity_conflict", rule)
    # Check the Core grammar with the actual engine, but no data or external loads.
    import pyshacl
    from pyshacl.shapes_graph import ShapesGraph

    try:
        pyshacl.validate(
            Graph(),
            shacl_graph=Graph() + graph,
            meta_shacl=True,
            advanced=False,
            js=False,
            inference="none",
            do_owl_imports=False,
            sparql_mode=False,
            max_validation_depth=16,
        )
        # pySHACL augments its shapes graph with vocabulary axioms on discovery.
        # Neither those axioms nor its mutable graph should enter the compiled rule.
        for shape in ShapesGraph(Graph() + graph).shapes:
            graph.add((shape.node, SH.severity, expected))
    except Exception as exc:
        raise _invalid("invalid_shacl_shape", rule) from exc
    nodes = {subject: BNode() for subject in subjects}
    isolated = Graph()
    for subject, predicate, obj in graph:
        isolated.add((nodes[subject], predicate, nodes.get(obj, obj)))
    return isolated


def compile_ontology_rules(
    rules: list[dict[str, object]], kinds: dict[str, ResourceKind]
) -> CompiledOntologyRules:
    """Compile without database access, network resolution or changing rule payloads."""
    compiled = CompiledOntologyRules(tbox=Graph(), shapes=Graph())
    total_bytes = 0
    for record in rules:
        rule = _rule_payload(record)
        language = rule.get("language")
        if language is not None and not isinstance(language, str):
            raise _invalid("unsupported_rule_language", rule)
        if language not in {"OWL", "SHACL"}:
            if language is not None and language not in {"DATA", "DERIVATION"}:
                raise _invalid("unsupported_rule_language", rule)
            continue
        target, expression = rule.get("target_iri"), rule.get("expression")
        if not isinstance(target, str) or target not in kinds:
            raise _invalid("rule_target_not_frozen", rule)
        if not isinstance(expression, str):
            raise _invalid("rule_expression_required", rule)
        total_bytes += len(expression.encode("utf-8"))
        if total_bytes > MAX_TEXT_BYTES:
            raise _invalid("rule_text_budget_exceeded", rule)
        try:
            graph = _parse(expression, "expression")
            if language == "OWL":
                destination = compiled.tbox
                graph = _compile_owl(graph, target, kinds, rule)
            else:
                destination = compiled.shapes
                graph = _compile_shapes(graph, target, kinds, rule)
            for triple in graph:
                destination.add(triple)
            if len(compiled.tbox) + len(compiled.shapes) > MAX_TRIPLES:
                raise _invalid("too_many_rule_triples", rule)
        except KGError as exc:
            raise _invalid(str(exc.params.get("reason", "invalid_rule")), rule) from exc
    return compiled


def read_rule_annotations(graph: Graph, ontology_iri: str) -> list[dict[str, object]]:
    """Recover rule payloads without executing them; full asset restore stays strict."""
    rules: list[dict[str, object]] = []
    for value in graph.objects(URIRef(ontology_iri), URIRef(_KG + "ruleSnapshot")):
        if not isinstance(value, Literal):
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION, {"reason": "invalid_rule_annotation"}
            )
        try:
            rule = json.loads(str(value))
        except ValueError as exc:
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION, {"reason": "invalid_rule_annotation"}
            ) from exc
        if not isinstance(rule, dict):
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION, {"reason": "invalid_rule_annotation"}
            )
        rules.append(rule)
    return rules
