"""B-semantics: actual exported rules/path execution, with no database or network."""

from __future__ import annotations

import json
import socket
from copy import deepcopy

import pytest
from app.core.errors import KGError
from app.models.enums import ResourceKind, ValidationState
from app.schemas.ontology import OntologyExportFormat
from app.semantics.ontology_rdf import (
    OntologyRdfMetadata,
    OntologyRdfResource,
    serialize_ontology_rdf,
)
from app.semantics.ontology_restore import parse_restore_document
from app.semantics.ontology_rules import compile_ontology_rules, read_rule_annotations
from app.semantics.rdflib_backend import RdflibBackend
from rdflib import RDF, RDFS, SH, BNode, Graph, Namespace, URIRef
from rdflib.compare import isomorphic

EX = Namespace("https://example.org/rules#")
ROOT = "https://example.org/ontology/rules"
PREFIX = """
@prefix ex: <https://example.org/rules#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
"""


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


@pytest.fixture()
def snapshots() -> dict[int, OntologyRdfResource]:
    result: dict[int, OntologyRdfResource] = {}
    for index, name in enumerate(["A", "B", "C", "Rel", "Back"], start=1):
        result[index] = OntologyRdfResource.model_validate(
            {
                "name": name,
                "iri": str(EX[name]),
                "kind": "ENTITY" if index < 4 else "OBJECT_PROP",
                "namespace": {"prefix": "ex", "iri": str(EX)},
                "parent_ids": [],
                "resource_refs": [],
            }
        )
    result[4].resource_refs = (
        type(result[4])
        .model_validate(
            {
                **result[4].model_dump(),
                "resource_refs": [
                    {"role": "relation_domain", "target_id": 1},
                    {"role": "relation_range", "target_id": 2},
                ],
            }
        )
        .resource_refs
    )
    result[4].object_prop = {
        "domain_cardinality": {"min": 0, "max": -1},
        "range_cardinality": {"min": 1, "max": 1},
    }
    return result


def rule(
    expression: str, *, language: str = "OWL", target: str = "A"
) -> dict[str, object]:
    return {
        "identifier": "RULE-1",
        "revision": 2,
        "target_iri": str(EX[target]),
        "language": language,
        "expression": PREFIX + expression,
        "severity": "VIOLATION",
        "execution": "AUTO",
    }


def exported(
    snapshots: dict[int, OntologyRdfResource],
    rules: list[dict[str, object]],
    rdf_format: OntologyExportFormat = OntologyExportFormat.TURTLE,
) -> str:
    return serialize_ontology_rdf(
        OntologyRdfMetadata(
            name="Rules", iri=ROOT, label_i18n=None, definition_i18n=None
        ),
        snapshots,
        revision=3,
        rdf_format=rdf_format,
        rules=rules,
    )


def frozen_record(payload: dict[str, object]) -> dict[str, object]:
    return {
        "rule_id": 17,
        "identifier": payload["identifier"],
        "revision": payload["revision"],
        "snapshot": {**payload, "id": 17},
    }


def kinds(snapshots: dict[int, OntologyRdfResource]) -> dict[str, ResourceKind]:
    return {snapshot.iri: snapshot.kind for snapshot in snapshots.values()}


@pytest.mark.parametrize("rdf_format", list(OntologyExportFormat))
@pytest.mark.parametrize(
    ("count", "state"), [(0, "VIOLATION"), (1, "PASS"), (2, "VIOLATION")]
)
def test_exported_inverse_path_executes_real_cardinality(
    snapshots: dict[int, OntologyRdfResource],
    rdf_format: OntologyExportFormat,
    count: int,
    state: str,
) -> None:
    shapes = Graph().parse(
        data=exported(snapshots, [], rdf_format), format=rdf_format.value
    )
    inverse = next(shapes.subjects(SH.inversePath, EX.Rel))
    assert isinstance(inverse, BNode)
    data = Graph()
    data.add((EX.b, RDF.type, EX.B))
    for index in range(count):
        subject = EX[f"a{index}"]
        data.add((subject, RDF.type, EX.A))
        data.add((subject, EX.Rel, EX.b))
    report = RdflibBackend().validate(data, shapes_graph=shapes)
    assert report.state.value == state
    assert isinstance(report.raw, Graph)
    assert (None, RDF.type, SH.ValidationReport) in report.raw


@pytest.mark.parametrize("rdf_format", list(OntologyExportFormat))
@pytest.mark.parametrize("legacy", [False, True])
def test_inverse_path_restore_keeps_cardinality_and_old_uri_compatibility(
    snapshots: dict[int, OntologyRdfResource],
    rdf_format: OntologyExportFormat,
    legacy: bool,
) -> None:
    snapshots.pop(5)  # This cardinality fixture has only one complete relationship.
    graph = Graph().parse(data=exported(snapshots, []), format="turtle")
    if legacy:
        inverse = next(graph.subjects(SH.inversePath, EX.Rel))
        named = URIRef(f"{EX.Rel}#inverse-range")
        for subject, predicate, obj in list(graph):
            if inverse in (subject, obj):
                graph.remove((subject, predicate, obj))
                graph.add(
                    (
                        named if subject == inverse else subject,
                        predicate,
                        named if obj == inverse else obj,
                    )
                )
    document = parse_restore_document(
        rdf_format.value, graph.serialize(format=rdf_format.value)
    )
    assert document.issues == []
    relation = next(
        resource for resource in document.resources if resource.iri == str(EX.Rel)
    )
    assert relation.object_prop is not None
    assert relation.object_prop["range_cardinality"] == {
        "min": 1,
        "max": 1,
    }


@pytest.mark.parametrize("rdf_format", list(OntologyExportFormat))
@pytest.mark.parametrize("wrapped", [False, True])
def test_owl_rules_are_executable_and_annotations_round_trip(
    snapshots: dict[int, OntologyRdfResource],
    rdf_format: OntologyExportFormat,
    wrapped: bool,
) -> None:
    rules = [rule("ex:A rdfs:subClassOf ex:C . ex:C owl:disjointWith ex:B .")]
    if wrapped:
        rules = [frozen_record(payload) for payload in rules]
    before = deepcopy(rules)
    content = exported(snapshots, rules, rdf_format)
    assert rules == before
    graph = Graph().parse(data=content, format=rdf_format.value)
    assert read_rule_annotations(graph, ROOT) == rules
    second = Graph().parse(
        data=graph.serialize(format=rdf_format.value), format=rdf_format.value
    )
    assert isomorphic(graph, second)
    assert read_rule_annotations(second, ROOT) == rules
    backend = RdflibBackend()
    graph.add((EX.i, RDF.type, EX.A))
    inferred = backend.reason(graph)
    assert (EX.i, RDF.type, EX.C) in inferred.inferred
    assert (
        backend.check_consistency(graph.serialize(format="turtle")).state
        is ValidationState.PASS
    )
    graph.add((EX.i, RDF.type, EX.B))
    report = backend.check_consistency(graph.serialize(format="turtle"))
    assert report.state is ValidationState.VIOLATION
    assert report.raw["errors"]
    # Rule recovery is explicit; the full restore must never silently drop rules.
    document = parse_restore_document(rdf_format.value, content)
    assert document.issues and any(
        "ruleSnapshot" in triple for triple in document.unsupported_triples
    )


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("ex:A owl:equivalentClass ex:C .", (EX.i, RDF.type, EX.C)),
        ("ex:Rel owl:inverseOf ex:Back .", (EX.b, EX.Back, EX.i)),
        ("ex:Rel rdfs:subPropertyOf ex:Back .", (EX.i, EX.Back, EX.b)),
        ("ex:Rel owl:equivalentProperty ex:Back .", (EX.i, EX.Back, EX.b)),
        ("ex:Rel a owl:SymmetricProperty .", (EX.b, EX.Rel, EX.i)),
        ("ex:Rel a owl:TransitiveProperty .", (EX.i, EX.Rel, EX.c)),
        ("ex:Back rdfs:domain ex:C .", (EX.i, RDF.type, EX.C)),
        ("ex:Back rdfs:range ex:C .", (EX.b, RDF.type, EX.C)),
    ],
)
def test_named_owl_subset_changes_real_inference(
    snapshots: dict[int, OntologyRdfResource],
    expression: str,
    expected: tuple[URIRef, URIRef, URIRef],
) -> None:
    target = (
        "A"
        if expression.startswith("ex:A")
        else "Back"
        if expression.startswith("ex:Back")
        else "Rel"
    )
    facts = "ex:i a ex:A ; ex:Rel ex:b . ex:b ex:Rel ex:c ."
    if target == "Back":
        facts += " ex:i ex:Back ex:b ."
    data = Graph().parse(data=PREFIX + facts, format="turtle")
    backend = RdflibBackend()
    baseline = backend.reason(Graph() + data)
    assert expected not in baseline.inferred
    compiled = compile_ontology_rules(
        [rule(expression, target=target)], kinds(snapshots)
    )
    report = backend.reason(data + compiled.tbox)
    assert expected in report.inferred
    assert len(compiled.shapes) == 0


@pytest.mark.parametrize(
    ("feature", "target", "facts", "difference"),
    [
        (
            "FunctionalProperty",
            "Rel",
            "ex:i ex:Rel ex:b, ex:c .",
            "ex:b owl:differentFrom ex:c .",
        ),
        (
            "InverseFunctionalProperty",
            "Rel",
            "ex:i ex:Rel ex:b . ex:j ex:Rel ex:b .",
            "ex:i owl:differentFrom ex:j .",
        ),
    ],
)
def test_owl_functionality_is_identity_inference_not_closed_world_uniqueness(
    snapshots: dict[int, OntologyRdfResource],
    feature: str,
    target: str,
    facts: str,
    difference: str,
) -> None:
    compiled = compile_ontology_rules(
        [rule(f"ex:Rel a owl:{feature} .", target=target)], kinds(snapshots)
    )
    graph = compiled.tbox + Graph().parse(data=PREFIX + facts, format="turtle")
    backend = RdflibBackend()
    assert (
        backend.check_consistency(graph.serialize(format="turtle")).state
        is ValidationState.PASS
    )
    graph += Graph().parse(data=PREFIX + difference, format="turtle")
    assert (
        backend.check_consistency(graph.serialize(format="turtle")).state
        is ValidationState.VIOLATION
    )


@pytest.mark.parametrize("rdf_format", list(OntologyExportFormat))
@pytest.mark.parametrize("wrapped", [False, True])
def test_shacl_rules_are_separate_isolated_and_actually_validate(
    snapshots: dict[int, OntologyRdfResource],
    rdf_format: OntologyExportFormat,
    wrapped: bool,
) -> None:
    rules = [
        rule(
            "ex:S a sh:NodeShape ; sh:targetClass ex:A ; "
            "sh:property [ sh:path ex:Rel ; sh:minCount 1 ] .",
            language="SHACL",
        ),
        rule(
            "ex:S a sh:NodeShape ; sh:targetClass ex:A ; "
            "sh:property [ sh:path ex:Back ; sh:minCount 1 ] .",
            language="SHACL",
        ),
    ]
    if wrapped:
        rules = [frozen_record(payload) for payload in rules]
    compiled = compile_ontology_rules(rules, kinds(snapshots))
    assert not compiled.tbox
    assert len(list(compiled.shapes.subjects(SH.targetClass, EX.A))) == 2
    exported_graph = Graph().parse(
        data=exported(snapshots, rules, rdf_format), format=rdf_format.value
    )
    assert sorted(
        json.dumps(value, sort_keys=True)
        for value in read_rule_annotations(exported_graph, ROOT)
    ) == sorted(json.dumps(value, sort_keys=True) for value in rules)
    backend = RdflibBackend()
    for shapes in (compiled.shapes, exported_graph):
        data = Graph().parse(
            data=PREFIX + "ex:i a ex:A ; ex:Rel ex:b ; ex:Back ex:b . ex:b a ex:B .",
            format="turtle",
        )
        assert backend.validate(data, shapes_graph=shapes).state is ValidationState.PASS
        data.remove((EX.i, EX.Rel, EX.b))
        assert (
            backend.validate(data, shapes_graph=shapes).state
            is ValidationState.VIOLATION
        )


@pytest.mark.parametrize(
    "expression",
    [
        "ex:A rdfs:subClassOf [ a owl:Restriction ; "
        "owl:onProperty ex:Rel ; owl:maxCardinality 1 ] .",
        "ex:Rel owl:propertyChainAxiom ( ex:Back ex:Rel ) .",
        "ex:A owl:imports <https://example.org/remote> .",
        "ex:A owl:equivalentClass <https://example.org/unknown> .",
        "ex:A rdfs:subClassOf ex:Rel .",
        "ex:i a ex:A .",
        "ex:A a owl:Class .",
        "ex:A a owl:Class . ex:B owl:equivalentClass ex:C .",
        "@prefix owl: <http://www.w3.org/2002/07/owl#> . "
        "ex:A owl:impor\\u0074s <file:///private/tmp/never-read> .",
        '{"@context": "https://example.org/remote"}',
        "this is not turtle",
        "",
    ],
)
def test_unsupported_owl_rule_blocks_export_instead_of_passing(
    snapshots: dict[int, OntologyRdfResource], expression: str
) -> None:
    with pytest.raises(KGError) as caught:
        exported(snapshots, [rule(expression)])
    assert caught.value.code.value == "KG.VALIDATION_VIOLATION"
    assert caught.value.params["rule_identifier"] == "RULE-1"


@pytest.mark.parametrize(
    "body",
    [
        "sh:sparql [ sh:select 'SELECT * WHERE { "
        "SERVICE <https://example.org> { ?s ?p ?o } }' ]",
        "sh:property [ sh:path <https://example.org/unknown> ; sh:minCount 1 ]",
        "sh:property [ sh:path ex:Rel ; sh:minCount 'invalid' ]",
        "sh:property [ sh:path ex:Rel ; sh:node [ sh:js 'evil()' ] ]",
        "sh:property [ sh:path ex:Rel ; sh:severity sh:Warning ]",
    ],
)
def test_unsafe_or_invalid_shacl_is_rejected(
    snapshots: dict[int, OntologyRdfResource], body: str
) -> None:
    with pytest.raises(KGError):
        exported(
            snapshots,
            [
                rule(
                    f"ex:S a sh:NodeShape ; sh:targetClass ex:A ; {body} .",
                    language="SHACL",
                )
            ],
        )


def test_frozen_payload_input_is_unchanged_and_never_resolved_live(
    snapshots: dict[int, OntologyRdfResource],
) -> None:
    rules = [rule("ex:A rdfs:subClassOf ex:C .")]
    before = [dict(item) for item in rules]
    compiled = compile_ontology_rules(rules, kinds(snapshots))
    assert rules == before
    assert (EX.A, RDFS.subClassOf, EX.C) in compiled.tbox
    snapshots.pop(3)
    with pytest.raises(KGError):
        compile_ontology_rules(rules, kinds(snapshots))


def test_inverse_path_preserves_repeatable_json_ld_exports(
    snapshots: dict[int, OntologyRdfResource],
) -> None:
    first = exported(snapshots, [], OntologyExportFormat.JSON_LD)
    assert exported(snapshots, [], OntologyExportFormat.JSON_LD) == first


def test_rule_text_budget_is_bounded_across_rules(
    snapshots: dict[int, OntologyRdfResource],
) -> None:
    expression = "ex:A rdfs:subClassOf ex:C . #" + "x" * 33000
    with pytest.raises(KGError) as caught:
        compile_ontology_rules([rule(expression), rule(expression)], kinds(snapshots))
    assert caught.value.params["reason"] == "rule_text_budget_exceeded"


@pytest.mark.parametrize(
    "override",
    [
        {"snapshot": None},
        {"snapshot": {}},
        {"revision": 99},
        {"revision": True},
        {"rule_id": 99},
        {"identifier": "different"},
    ],
)
def test_invalid_pinned_rule_never_falls_back_to_annotation_only(
    snapshots: dict[int, OntologyRdfResource], override: dict[str, object]
) -> None:
    record = frozen_record(rule("ex:A owl:equivalentClass ex:C ."))
    record.update(override)
    with pytest.raises(KGError) as caught:
        exported(snapshots, [record])
    assert caught.value.params["reason"] in {
        "missing_rule_snapshot",
        "mismatched_rule_snapshot",
    }


@pytest.mark.parametrize("language", [None, "EXTERNAL", ["OWL"], {"kind": "OWL"}])
def test_malformed_pinned_language_is_a_structured_rejection(
    snapshots: dict[int, OntologyRdfResource], language: object
) -> None:
    payload = rule("ex:A owl:equivalentClass ex:C .")
    payload["language"] = language
    with pytest.raises(KGError) as caught:
        exported(snapshots, [frozen_record(payload)])
    assert caught.value.params["reason"] == "unsupported_rule_language"
