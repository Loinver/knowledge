"""Offline AUTO rule execution on fixed data, using real OWL RL/SHACL engines."""

from __future__ import annotations

import json
import socket
import subprocess
from copy import deepcopy
from typing import Any

import pytest
from app.models.enums import ValidationState
from app.semantics import ontology_rule_validation as runner
from app.semantics.ontology_rdf import OntologyRdfMetadata, OntologyRdfResource
from rdflib import Graph

NS = "https://example.org/auto#"
PREFIX = f"""
@prefix ex: <{NS}> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
"""
METADATA = OntologyRdfMetadata(
    name="AutoRules",
    iri="https://example.org/ontology/auto",
    label_i18n=None,
    definition_i18n=None,
)


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Unexpected network access")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


@pytest.fixture()
def snapshots() -> dict[int, OntologyRdfResource]:
    def resource(name: str, **extra: Any) -> OntologyRdfResource:
        return OntologyRdfResource.model_validate(
            {
                "name": name,
                "iri": NS + name,
                "kind": "ENTITY",
                "namespace": {"prefix": "ex", "iri": NS},
                "parent_ids": [],
                "resource_refs": [],
                **extra,
            }
        )

    return {
        1: resource(
            "Person",
            resource_refs=[{"role": "data_prop", "target_id": 5}],
            datatype_props=[
                {
                    "name": "code",
                    "iri": NS + "Person/code",
                    "datatype": "string",
                    "nullable": True,
                    "min_cardinality": 0,
                    "max_cardinality": 1,
                    "min_value": None,
                    "max_value": None,
                }
            ],
        ),
        2: resource("Employee", parent_ids=[1]),
        3: resource("Organization"),
        4: resource(
            "Link",
            kind="OBJECT_PROP",
            resource_refs=[
                {"role": "relation_domain", "target_id": 1},
                {"role": "relation_range", "target_id": 3},
            ],
            object_prop={
                "domain_cardinality": {"min": 0, "max": -1},
                "range_cardinality": {"min": 0, "max": -1},
            },
        ),
        5: resource("Person.code", iri=NS + "Person/code", kind="DATATYPE_PROP"),
    }


def rule(
    expression: str, language: str = "SHACL", target: str = "Person", **extra: Any
) -> dict[str, Any]:
    payload = {
        "id": 17,
        "identifier": "AUTO-1",
        "revision": 2,
        "language": language,
        "target_iri": NS + target,
        "expression": PREFIX + expression,
        "severity": "VIOLATION",
        "execution": "AUTO",
        **extra,
    }
    return {
        "rule_id": payload["id"],
        "identifier": payload["identifier"],
        "revision": payload["revision"],
        "snapshot": payload,
    }


REQUIRED_CODE = (
    "ex:S a sh:NodeShape ; sh:targetClass ex:Person ; "
    "sh:property [ sh:path <https://example.org/auto#Person/code> ; sh:minCount 1 ] ."
)
INVERSE_ONE = (
    "ex:S a sh:NodeShape ; sh:targetClass ex:Organization ; "
    "sh:property [ sh:path [ sh:inversePath ex:Link ] ; "
    "sh:minCount 1 ; sh:maxCount 1 ] ."
)


def execute(
    snapshots: dict[int, OntologyRdfResource],
    rules: list[dict[str, Any]],
    data: str | dict[str, Any],
    **extra: Any,
) -> list[runner.OntologyRuleValidationResult]:
    return runner.validate_ontology_auto_rules(
        metadata=METADATA,
        snapshots=snapshots,
        rules=rules,
        instance_graph=data,
        revision=3,
        **extra,
    )


@pytest.mark.parametrize("valid", [False, True])
@pytest.mark.parametrize("structured", [False, True])
def test_real_shacl_on_subclass_attributes_preserves_input(
    snapshots: dict[int, OntologyRdfResource], valid: bool, structured: bool
) -> None:
    rules = [rule(REQUIRED_CODE)]
    data: str | dict[str, Any]
    if structured:
        data = {
            "entities": [
                {
                    "iri": NS + "alice",
                    "type_iri": NS + "Employee",
                    "attrs": {"code": "A"} if valid else {},
                }
            ]
        }
    else:
        data = PREFIX + "ex:alice a ex:Employee ."
        if valid:
            data += ' ex:alice <https://example.org/auto#Person/code> "A" .'
    before = deepcopy((rules, data))
    result = execute(snapshots, rules, data)[0]
    assert result.state is (
        ValidationState.PASS if valid else ValidationState.VIOLATION
    )
    assert result.detail["target_count"] == 1
    assert result.detail["ontology_iri"] == METADATA.iri
    assert result.detail["ontology_revision"] == 3
    if not valid:
        assert result.hits[0]["focus"] == NS + "alice"
        assert result.hits[0]["detail"]["path"] == NS + "Person/code"
        assert (
            "MinCountConstraintComponent"
            in result.hits[0]["detail"]["constraint_component"]
        )
    assert (rules, data) == before


@pytest.mark.parametrize("count", [0, 1, 2])
def test_real_inverse_shacl_reports_zero_one_many_and_source_ids(
    snapshots: dict[int, OntologyRdfResource], count: int
) -> None:
    data = {
        "entities": [{"iri": NS + "org", "type_iri": NS + "Organization"}]
        + [
            {"iri": NS + f"person{index}", "type_iri": NS + "Person"}
            for index in range(count)
        ],
        "triples": [
            {
                "id": index + 100,
                "subject": NS + f"person{index}",
                "predicate": "Link",
                "object_": NS + "org",
            }
            for index in range(count)
        ],
    }
    result = execute(snapshots, [rule(INVERSE_ONE, target="Organization")], data)[0]
    assert result.state is (
        ValidationState.PASS if count == 1 else ValidationState.VIOLATION
    )
    if count != 1:
        assert result.hits[0]["focus"] == NS + "org"
        assert result.hits[0]["triple_ids"] == list(range(100, 100 + count))
        assert result.hits[0]["detail"]["inverse"] is True
        assert result.hits[0]["detail"]["path"] == NS + "Link"


@pytest.mark.parametrize("rdf_format", ["turtle", "json-ld"])
@pytest.mark.parametrize("conflict", [False, True])
def test_actual_owl_disjoint_consistency_and_focus(
    snapshots: dict[int, OntologyRdfResource], rdf_format: str, conflict: bool
) -> None:
    text = PREFIX + "ex:alice a ex:Employee ."
    if conflict:
        text += " ex:alice a ex:Organization ."
    data = Graph().parse(data=text, format="turtle").serialize(format=rdf_format)
    result = execute(
        snapshots,
        [rule("ex:Person owl:disjointWith ex:Organization .", "OWL")],
        data,
        rdf_format=rdf_format,
    )[0]
    assert result.state is (
        ValidationState.VIOLATION if conflict else ValidationState.PASS
    )
    assert result.detail["engine"] == "owlrl_owl2_rl"
    if conflict:
        assert result.detail["errors"]
        assert result.hits and all(hit["focus"] == NS + "alice" for hit in result.hits)
        assert result.hits[0]["detail"]["reason"] == "owl_disjoint_class_conflict"


def test_combined_owl_rules_cannot_miss_interacting_contradictions(
    snapshots: dict[int, OntologyRdfResource],
) -> None:
    rules = [
        rule("ex:Person rdfs:subClassOf ex:Employee .", "OWL"),
        rule(
            "ex:Employee owl:disjointWith ex:Organization .",
            "OWL",
            "Employee",
            identifier="AUTO-2",
            id=18,
        ),
    ]
    results = execute(
        snapshots, rules, PREFIX + "ex:alice a ex:Person, ex:Organization ."
    )
    assert all(result.state is ValidationState.VIOLATION for result in results)
    assert all(result.detail["scope"] == "combined_tbox" for result in results)


def test_owl_equivalence_targets_are_available_to_shacl(
    snapshots: dict[int, OntologyRdfResource],
) -> None:
    rules = [
        rule("ex:Person owl:equivalentClass ex:Employee .", "OWL"),
        rule(
            REQUIRED_CODE.replace(
                "sh:targetClass ex:Person", "sh:targetClass ex:Employee"
            ),
            "SHACL",
            "Employee",
            identifier="AUTO-2",
            id=18,
        ),
    ]
    results = execute(snapshots, rules, PREFIX + "ex:alice a ex:Person .")
    assert results[0].state is ValidationState.PASS
    assert results[1].state is ValidationState.VIOLATION
    assert results[1].hits[0]["focus"] == NS + "alice"


@pytest.mark.parametrize("different", [False, True])
def test_functional_owl_obeys_open_world_identity(
    snapshots: dict[int, OntologyRdfResource], different: bool
) -> None:
    data = (
        PREFIX + "ex:p a ex:Person ; ex:Link ex:a, ex:b . "
        "ex:a a ex:Organization . ex:b a ex:Organization ."
    )
    if different:
        data += " ex:a owl:differentFrom ex:b ."
    result = execute(
        snapshots, [rule("ex:Link a owl:FunctionalProperty .", "OWL", "Link")], data
    )[0]
    assert result.state is (
        ValidationState.VIOLATION if different else ValidationState.PASS
    )
    if different:
        assert {hit["focus"] for hit in result.hits} == {NS + "a", NS + "b"}


@pytest.mark.parametrize("language", ["OWL", "SHACL"])
def test_empty_target_population_is_na_not_pass(
    snapshots: dict[int, OntologyRdfResource], language: str
) -> None:
    expression = (
        "ex:Person owl:equivalentClass ex:Employee ."
        if language == "OWL"
        else REQUIRED_CODE
    )
    result = execute(snapshots, [rule(expression, language)], {"entities": []})[0]
    assert result.state is ValidationState.NA
    assert result.detail["target_count"] == 0


@pytest.mark.parametrize(
    "override",
    [
        {"snapshot": None},
        {"revision": 99},
        {"rule_id": True},
    ],
)
def test_invalid_frozen_record_is_not_run(
    snapshots: dict[int, OntologyRdfResource], override: dict[str, Any]
) -> None:
    record = rule(REQUIRED_CODE)
    record.update(override)
    result = execute(snapshots, [record], PREFIX + "ex:alice a ex:Person .")[0]
    assert result.state is ValidationState.NOT_RUN


@pytest.mark.parametrize(
    "expression",
    [
        "ex:Person rdfs:subClassOf [ a owl:Restriction ; "
        "owl:onProperty ex:Link ; owl:maxCardinality 1 ] .",
        "ex:Person owl:imports <https://example.org/remote> .",
        "ex:Person owl:disjointWith <https://example.org/missing> .",
    ],
)
def test_unsupported_owl_is_not_run_even_without_targets(
    snapshots: dict[int, OntologyRdfResource], expression: str
) -> None:
    result = execute(snapshots, [rule(expression, "OWL")], {"entities": []})[0]
    assert result.state is ValidationState.NOT_RUN


@pytest.mark.parametrize(
    "data",
    [
        PREFIX + "ex:Person rdfs:subClassOf ex:Organization . ex:alice a ex:Person .",
        PREFIX + "ex:Person a owl:Class .",
        PREFIX + "ex:alice a ex:Unknown .",
        PREFIX + "ex:alice owl:imports <file:///private/tmp/never-read> .",
        {
            "entities": [
                {
                    "iri": NS + "alice",
                    "type_iri": NS + "Person",
                    "attrs": {"unknown": "x"},
                }
            ]
        },
        {"entities": [{"iri": NS + "alice", "type_iri": NS + "Unknown"}]},
        {
            "entities": [{"iri": NS + "alice", "type_iri": NS + "Person"}],
            "triples": [
                {
                    "subject": NS + "alice",
                    "predicate": "Link",
                    "object_": NS + "unknown",
                }
            ],
        },
    ],
)
def test_instance_cannot_inject_tbox_or_use_unknown_definitions(
    snapshots: dict[int, OntologyRdfResource], data: str | dict[str, Any]
) -> None:
    result = execute(snapshots, [rule(REQUIRED_CODE)], data)[0]
    assert result.state is ValidationState.NOT_RUN
    assert result.hits == []


def test_external_json_ld_context_is_rejected_before_fetch(
    snapshots: dict[int, OntologyRdfResource],
) -> None:
    result = execute(
        snapshots,
        [rule(REQUIRED_CODE)],
        json.dumps({"@context": "https://example.org/context", "@id": NS + "alice"}),
        rdf_format="json-ld",
    )[0]
    assert result.state is ValidationState.NOT_RUN
    assert result.reason == "external_json_ld_context"


def test_missing_property_snapshot_is_not_run_for_text_and_structured_data(
    snapshots: dict[int, OntologyRdfResource],
) -> None:
    snapshots[1].datatype_props = []
    for data in (PREFIX + "ex:alice a ex:Person .", {"entities": []}):
        result = execute(snapshots, [rule(REQUIRED_CODE)], data)[0]
        assert result.state is ValidationState.NOT_RUN


@pytest.mark.parametrize("execution", ["MANUAL", "UNKNOWN"])
def test_non_auto_rules_do_not_execute(
    snapshots: dict[int, OntologyRdfResource], execution: str
) -> None:
    result = execute(
        snapshots,
        [rule(REQUIRED_CODE, execution=execution)],
        PREFIX + "ex:alice a ex:Person .",
    )[0]
    assert result.state is ValidationState.NOT_RUN


@pytest.mark.parametrize("failure", ["timeout", "engine", "bad_response"])
def test_runner_failure_never_becomes_pass_and_releases_slot(
    snapshots: dict[int, OntologyRdfResource],
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    def failed(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if failure == "timeout":
            raise subprocess.TimeoutExpired("runner", 1)
        return subprocess.CompletedProcess(
            [], 1 if failure == "engine" else 0, "{}", ""
        )

    monkeypatch.setattr(runner.subprocess, "run", failed)
    for _ in range(3):
        result = execute(snapshots, [rule(REQUIRED_CODE)], {"entities": []})[0]
        assert result.state is ValidationState.NOT_RUN
        assert result.reason != "rule_runner_busy"


def test_reserved_vocabulary_cannot_be_frozen_as_an_instance_property(
    snapshots: dict[int, OntologyRdfResource],
) -> None:
    snapshots[4].iri = "http://www.w3.org/2002/07/owl#equivalentClass"
    data = {
        "entities": [
            {"iri": NS + "alice", "type_iri": NS + "Person"},
            {"iri": NS + "org", "type_iri": NS + "Organization"},
        ],
        "triples": [
            {"subject": NS + "alice", "predicate": "Link", "object_": NS + "org"}
        ],
    }
    result = execute(snapshots, [rule(REQUIRED_CODE)], data)[0]
    assert result.state is ValidationState.NOT_RUN
    assert result.reason == "reserved_snapshot_identity"


def test_real_worker_timeout_waits_for_child_termination(
    snapshots: dict[int, OntologyRdfResource], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = subprocess.Popen
    children: list[subprocess.Popen[Any]] = []

    def tracked(*args: Any, **kwargs: Any) -> subprocess.Popen[Any]:
        process = original(*args, **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(runner.subprocess, "Popen", tracked)
    monkeypatch.setattr(runner, "TIMEOUT_SECONDS", 0.001)
    result = execute(snapshots, [rule(REQUIRED_CODE)], {"entities": []})[0]
    assert result.state is ValidationState.NOT_RUN
    assert result.reason == "rule_runner_timeout"
    assert len(children) == 1 and children[0].poll() is not None


@pytest.mark.parametrize("structured", [False, True])
def test_implemented_any_uri_datatype_executes_in_auto_shapes(
    snapshots: dict[int, OntologyRdfResource], structured: bool
) -> None:
    snapshots[1].datatype_props[0]["datatype"] = "anyURI"
    expression = REQUIRED_CODE.replace(
        "sh:minCount 1",
        "sh:minCount 1 ; sh:datatype <http://www.w3.org/2001/XMLSchema#anyURI>",
    )
    data: str | dict[str, Any]
    if structured:
        data = {
            "entities": [
                {
                    "iri": NS + "alice",
                    "type_iri": NS + "Person",
                    "attrs": {"code": "../资料#条款"},
                }
            ]
        }
    else:
        data = (
            PREFIX + "ex:alice a ex:Person ; "
            '<https://example.org/auto#Person/code> "../资料#条款"'
            "^^<http://www.w3.org/2001/XMLSchema#anyURI> ."
        )
    result = execute(snapshots, [rule(expression)], data)[0]
    assert result.state is ValidationState.PASS
    bad_data = (
        PREFIX + "ex:alice a ex:Person ; "
        '<https://example.org/auto#Person/code> "plain-string" .'
    )
    assert (
        execute(snapshots, [rule(expression)], bad_data)[0].state
        is ValidationState.VIOLATION
    )
