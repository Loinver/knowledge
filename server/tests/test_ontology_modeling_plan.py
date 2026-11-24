"""Offline candidate boundary and plan tests; no database or model fixtures."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from app.domain.ontology_modeling_plan import compile_candidate
from app.schemas.ontology_modeling_candidate import (
    MAX_CANDIDATE_BYTES,
    MAX_CANDIDATE_DEPTH,
    CandidateErrorCode,
    CandidateParseError,
    OntologyCandidate,
    parse_candidate_json,
)

NS = {
    "ns:business": {"id": 1, "iri": "https://example.org/business#", "protected": False}
}
SOURCES = {"src:input": {"span:one": "虚构业务输入，仅用于测试。"}}


def metadata(label: str) -> dict[str, Any]:
    return {
        "labels": {"zh-CN": label, "en-US": None},
        "definitions": {"zh-CN": None, "en-US": None},
        "synonyms": [],
    }


def evidence() -> dict[str, Any]:
    return {
        "basis": "PROPOSAL",
        "source_refs": [],
        "rationale_i18n": {"zh-CN": "人工待审的业务建议", "en-US": None},
        "depends_on": [],
        "uncertainty_ids": [],
    }


def ref(cid: str) -> dict[str, Any]:
    return {"kind": "CANDIDATE", "candidate_id": cid}


def catalog_ref(handle: str = "asset:person") -> dict[str, Any]:
    return {"kind": "CATALOG", "handle": handle}


def new_class(cid: str, name: str, label: str) -> dict[str, Any]:
    return {
        "candidate_id": cid,
        "spec": {
            "kind": "NEW_CLASS",
            "namespace_handle": "ns:business",
            "local_name": name,
            "metadata": metadata(label),
            "parents": [],
        },
        "evidence": evidence(),
    }


def data_property(cid: str = "c:age", datatype: str = "integer") -> dict[str, Any]:
    return {
        "candidate_id": cid,
        "spec": {
            "kind": "NEW_DATA_PROPERTY",
            "namespace_handle": "ns:business",
            "local_name": cid.split(":")[1],
            "metadata": metadata(cid),
            "owner": ref("c:person"),
            "datatype": datatype,
        },
        "evidence": evidence(),
    }


def relation(
    cid: str = "c:owns", inverse: str | None = None, reverse: bool = False
) -> dict[str, Any]:
    return {
        "candidate_id": cid,
        "spec": {
            "kind": "NEW_OBJECT_PROPERTY",
            "namespace_handle": "ns:business",
            "local_name": cid.split(":")[1],
            "metadata": metadata(cid),
            "domain": {
                "mode": "ONE",
                "refs": [ref("c:device" if reverse else "c:person")],
            },
            "range": {
                "mode": "ONE",
                "refs": [ref("c:person" if reverse else "c:device")],
            },
            "inverse_of": ref(inverse) if inverse else None,
            "features": dict.fromkeys(
                (
                    "functional",
                    "inverse_functional",
                    "symmetric",
                    "transitive",
                    "asymmetric",
                    "reflexive",
                    "irreflexive",
                ),
                False,
            ),
        },
        "evidence": evidence(),
    }


def constraint(kind: str, **fields: Any) -> dict[str, Any]:
    return {
        "candidate_id": "c:rule",
        "target_class": ref("c:person"),
        "spec": {"kind": kind, **fields},
        "severity": "VIOLATION",
        "evidence": evidence(),
    }


def path(cid: str = "c:age", inverse: bool = False) -> dict[str, Any]:
    return {"property": ref(cid), "inverse": inverse}


def candidate() -> dict[str, Any]:
    return {
        "schema_version": "ontology-candidate/1.0",
        "context_token": "context:one",
        "profile_echo": "BUSINESS",
        "scope": {
            "goal_i18n": {"zh-CN": "建模虚构业务", "en-US": None},
            "out_of_scope_i18n": [],
            "assumptions_i18n": [],
        },
        "ontology_metadata": None,
        "resources": [
            new_class("c:person", "Person", "人员"),
            new_class("c:device", "Device", "设备"),
            data_property(),
        ],
        "axioms": [],
        "constraints": [],
        "questions": [],
    }


def compile_payload(payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return compile_candidate(
        parse_candidate_json(json.dumps(payload, ensure_ascii=False)),
        namespace_catalog=kwargs.pop("namespace_catalog", copy.deepcopy(NS)),
        asset_catalog=kwargs.pop("asset_catalog", {}),
        source_catalog=kwargs.pop("source_catalog", copy.deepcopy(SOURCES)),
        context_token=kwargs.pop("context_token", "context:one"),
        **kwargs,
    )


def blocked(payload: dict[str, Any], reason: str, **kwargs: Any) -> dict[str, Any]:
    plan = compile_payload(payload, **kwargs)
    assert plan["state"] == "BLOCKED"
    assert f"KG.CANDIDATE_{reason}" in {issue["code"] for issue in plan["issues"]}
    assert (
        plan["resources"]
        == plan["constraints"]
        == plan["inverse_links"]
        == plan["axioms"]
        == []
    )
    assert plan["metadata"] is None
    assert plan["canonical_candidate"]["schema_version"] == "ontology-candidate/1.0"
    assert all(issue["state"] in {"VIOLATION", "NOT_RUN"} for issue in plan["issues"])
    return plan


def asset(**fields: Any) -> dict[str, Any]:
    return {
        "asset:person": {
            "id": 10,
            "revision": 2,
            "kind": "CLASS",
            "iri": "https://example.org/assets#ExistingPerson",
            "name": "ExistingPerson",
            **fields,
        }
    }


@pytest.mark.parametrize(
    "class_length,property_length,allowed", [(100, 27, True), (100, 28, False)]
)
def test_composed_property_name_respects_storage_budget(
    class_length: int, property_length: int, allowed: bool
) -> None:
    payload = candidate()
    owner = new_class("c:person", "A" * class_length, "类型")
    prop = data_property()
    prop["spec"]["local_name"] = "a" * property_length
    payload["resources"] = [owner, prop]
    plan = compile_payload(payload)
    if allowed:
        assert plan["state"] == "COMPILED", plan["issues"]
    else:
        blocked(payload, "INVALID_NAME")


def test_compile_is_deterministic_pure_and_orders_real_dependencies() -> None:
    payload = candidate()
    payload["resources"].reverse()
    before = copy.deepcopy(payload)
    ns, sources = copy.deepcopy(NS), copy.deepcopy(SOURCES)
    plan = compile_payload(payload, namespace_catalog=ns, source_catalog=sources)
    assert plan["state"] == "COMPILED" and plan["issues"] == []
    assert plan == compile_payload(payload)
    assert payload == before and ns == NS and sources == SOURCES
    assert len(plan["digest"]) == 64
    operations = {item["candidate_id"]: item for item in plan["resources"]}
    ids = [item["candidate_id"] for item in plan["resources"]]
    assert ids.index("c:person") < ids.index("c:age")
    assert plan["dependencies"]["c:age"] == ["c:person"]  # Not supplied by model.
    assert operations["c:age"]["iri"] == operations["c:person"]["iri"] + "/age"
    assert operations["c:age"]["name"] == "Person.age"
    assert operations["c:person"]["metadata"]["labels"]["en-US"] is None
    assert operations["c:person"]["metadata"]["definitions"]["zh-CN"] is None
    assert "published" not in plan and "validation" not in plan
    payload["resources"].reverse()
    assert plan == compile_payload(payload)
    sources["src:input"]["span:one"] += "不同快照"
    assert compile_payload(payload, source_catalog=sources)["digest"] != plan["digest"]
    assert compile_payload(payload, asset_catalog=asset())["digest"] != plan["digest"]


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        "null",
        "{}",
        "{",
        "```json\n{}\n```",
        '{"x": NaN}',
        '{"x": Infinity}',
        b"\xff",
    ],
)
def test_bad_json_and_legacy_arrays_are_rejected(raw: str | bytes) -> None:
    with pytest.raises(CandidateParseError):
        parse_candidate_json(raw)


@pytest.mark.parametrize(
    "raw", ['{"schema_version":"x","schema_version":"y"}', '{"scope":{"x":1,"x":2}}']
)
def test_duplicate_json_keys_are_rejected_before_schema(raw: str) -> None:
    with pytest.raises(CandidateParseError, match="DUPLICATE_JSON_KEY"):
        parse_candidate_json(raw)


def test_json_budget_limits() -> None:
    for raw, reason in (
        (" " * (MAX_CANDIDATE_BYTES + 1), "TOO_LARGE"),
        (
            "[" * (MAX_CANDIDATE_DEPTH + 1) + "0" + "]" * (MAX_CANDIDATE_DEPTH + 1),
            "TOO_COMPLEX",
        ),
        (json.dumps({"x": [None] * 20_001}), "TOO_COMPLEX"),
    ):
        with pytest.raises(CandidateParseError, match=reason):
            parse_candidate_json(raw)
    payload = candidate()
    payload["resources"] = [payload["resources"][0]] * 201
    with pytest.raises(CandidateParseError, match="INVALID_STRUCTURE"):
        parse_candidate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "location,field,value",
    [
        ("top", "schema_version", "ontology-candidate/2.0"),
        ("top", "context_token", 42),
        ("top", "published", True),
        ("spec", "resource_id", 1),
        ("spec", "iri", "https://example.org/forged"),
        (
            "spec",
            "metadata",
            {"labels": {"zh-CN": "中文"}, "definitions": {}, "synonyms": []},
        ),
    ],
)
def test_unknown_fields_versions_and_strict_types(
    location: str, field: str, value: Any
) -> None:
    payload = candidate()
    target = payload if location == "top" else payload["resources"][0]["spec"]
    target[field] = value
    with pytest.raises(CandidateParseError):
        parse_candidate_json(json.dumps(payload))


def test_strict_numeric_boolean_and_no_error_input_echo() -> None:
    payload = candidate()
    payload["constraints"] = [constraint("CARDINALITY", path=path(), min=True, max="2")]
    with pytest.raises(CandidateParseError) as error:
        parse_candidate_json(json.dumps(payload))
    assert error.value.code == "KG.CANDIDATE_INVALID_STRUCTURE"
    assert all(set(item) == {"loc", "type"} for item in error.value.params["errors"])
    payload = candidate()
    payload["resources"].append(relation())
    payload["resources"][-1]["spec"]["features"]["functional"] = 1
    with pytest.raises(CandidateParseError):
        parse_candidate_json(json.dumps(payload))


@pytest.mark.parametrize("field", ["rationale_i18n", "labels"])
def test_blank_evidence_and_chinese_labels_rejected(field: str) -> None:
    payload = candidate()
    if field == "rationale_i18n":
        payload["resources"][0]["evidence"][field] = {"zh-CN": None, "en-US": None}
    else:
        payload["resources"][0]["spec"]["metadata"][field]["zh-CN"] = "  "
    with pytest.raises(CandidateParseError):
        parse_candidate_json(json.dumps(payload))


def test_sources_are_authoritative_handles_not_candidate_claims() -> None:
    payload = candidate()
    ev = payload["resources"][0]["evidence"]
    ev["basis"] = "SOURCE"
    with pytest.raises(CandidateParseError):
        parse_candidate_json(json.dumps(payload))
    ev["source_refs"] = [{"source_handle": "src:input", "span_handle": "span:one"}]
    assert compile_payload(payload)["state"] == "COMPILED"
    blocked(payload, "UNKNOWN_SOURCE_SPAN", source_catalog={})
    blocked(
        payload, "INVALID_SOURCE_SPAN", source_catalog={"src:input": {"span:one": "  "}}
    )
    ev["source_refs"][0]["quote"] = "假引文"
    with pytest.raises(CandidateParseError):
        parse_candidate_json(json.dumps(payload))


def test_references_namespaces_kinds_and_owner_namespace_are_checked() -> None:
    payload = candidate()
    payload["resources"][0]["spec"]["parents"] = [ref("c:missing")]
    blocked(payload, "UNKNOWN_REFERENCE")
    payload["resources"][0]["spec"]["parents"] = [ref("c:age")]
    blocked(payload, "REFERENCE_KIND")
    payload = candidate()
    payload["resources"][2]["spec"]["owner"] = ref("c:age")
    blocked(payload, "REFERENCE_KIND")
    payload = candidate()
    payload["resources"][0]["spec"]["namespace_handle"] = "ns:fake"
    blocked(payload, "UNKNOWN_NAMESPACE")
    payload = candidate()
    ns = copy.deepcopy(NS)
    ns["ns:other"] = {"id": 2, "iri": "https://example.org/other#", "protected": False}
    payload["resources"][2]["spec"]["namespace_handle"] = "ns:other"
    blocked(payload, "OWNER_NAMESPACE", namespace_catalog=ns)
    ns["ns:business"]["protected"] = True
    blocked(candidate(), "PROTECTED_NAMESPACE", namespace_catalog=ns)


def test_reuse_is_read_only_pinned_and_owner_reuse_unsupported() -> None:
    payload = candidate()
    reuse = {
        "candidate_id": "c:reuse",
        "spec": {
            "kind": "REUSE",
            "handle": "asset:person",
            "expected_kind": "CLASS",
            "attach_to_ontology": False,
        },
        "evidence": evidence(),
    }
    payload["resources"].append(reuse)
    plan = compile_payload(payload, asset_catalog=asset())
    operation = next(item for item in plan["resources"] if item["kind"] == "REUSE")
    assert operation["id"] == 10 and operation["revision"] == 2
    assert operation["attach_to_ontology"] is False and "metadata" not in operation
    blocked(payload, "UNKNOWN_REFERENCE")
    reuse["spec"]["expected_kind"] = "DATA_PROPERTY"
    blocked(payload, "REFERENCE_KIND", asset_catalog=asset())
    reuse["spec"]["expected_kind"] = "CLASS"
    payload["resources"][2]["spec"]["owner"] = ref("c:reuse")
    blocked(payload, "UNSUPPORTED", asset_catalog=asset())
    reuse["spec"]["metadata"] = metadata("禁止编辑")
    with pytest.raises(CandidateParseError):
        parse_candidate_json(json.dumps(payload))


@pytest.mark.parametrize("revision", [True, 0, "2"])
def test_invalid_catalog_pins_rejected(revision: Any) -> None:
    blocked(candidate(), "INVALID_CATALOG", asset_catalog=asset(revision=revision))


def test_duplicates_and_project_global_names() -> None:
    payload = candidate()
    payload["resources"].append(copy.deepcopy(payload["resources"][0]))
    blocked(payload, "DUPLICATE_ID")
    payload["resources"][-1]["candidate_id"] = "c:another"
    blocked(payload, "DUPLICATE_RESOURCE")
    payload = candidate()
    payload["resources"].append(new_class("c:another", "Another", "人员"))
    blocked(payload, "POSSIBLE_SYNONYM")
    payload = candidate()
    blocked(
        payload,
        "NEW_REQUIRES_REUSE",
        asset_catalog=asset(iri="https://example.org/business#Person"),
    )
    blocked(payload, "NEW_REQUIRES_REUSE", asset_catalog=asset(name="Person"))
    payload["resources"][0]["spec"]["local_name"] = "person"
    blocked(payload, "INVALID_NAME")


@pytest.mark.parametrize("self_cycle", [True, False])
def test_inheritance_and_declared_dependency_cycles(self_cycle: bool) -> None:
    payload = candidate()
    payload["resources"][0]["spec"]["parents"] = [
        ref("c:person" if self_cycle else "c:device")
    ]
    if not self_cycle:
        payload["resources"][1]["spec"]["parents"] = [ref("c:person")]
    blocked(payload, "DEPENDENCY_CYCLE")
    payload = candidate()
    payload["resources"][0]["evidence"]["depends_on"] = ["c:device"]
    payload["resources"][1]["evidence"]["depends_on"] = ["c:person"]
    blocked(payload, "DEPENDENCY_CYCLE")
    payload["resources"][0]["evidence"]["depends_on"] = ["c:fake"]
    blocked(payload, "UNKNOWN_DEPENDENCY")


def test_questions_are_unique_associated_and_cannot_demote_uncertainty() -> None:
    payload = candidate()
    payload["resources"][0]["evidence"]["uncertainty_ids"] = ["q:one"]
    blocked(payload, "UNKNOWN_QUESTION")
    question = {
        "id": "q:one",
        "question_i18n": {"zh-CN": "请确认", "en-US": None},
        "blocking": False,
        "related_candidate_ids": ["c:person"],
    }
    payload["questions"] = [question]
    plan = blocked(payload, "UNRESOLVED_UNCERTAINTY")
    assert next(
        i for i in plan["issues"] if i["code"].endswith("UNRESOLVED_UNCERTAINTY")
    )["blocking"]
    payload["questions"].append(copy.deepcopy(question))
    blocked(payload, "DUPLICATE_QUESTION")
    payload["questions"] = [question]
    question["related_candidate_ids"] = ["c:fake"]
    blocked(payload, "UNKNOWN_QUESTION_CANDIDATE")
    question["question_i18n"] = {"zh-CN": " ", "en-US": None}
    with pytest.raises(CandidateParseError):
        parse_candidate_json(json.dumps(payload))


@pytest.mark.parametrize("mutual", [False, True])
def test_inverse_pairs_use_second_phase_not_creation_cycles(mutual: bool) -> None:
    payload = candidate()
    payload["resources"] += [
        relation(inverse="c:belongs"),
        relation("c:belongs", "c:owns" if mutual else None, reverse=True),
    ]
    if mutual:
        payload["resources"][-1]["evidence"]["depends_on"] = ["c:owns"]
        payload["resources"][-2]["evidence"]["depends_on"] = ["c:belongs"]
    plan = compile_payload(payload)
    assert plan["state"] == "COMPILED" and len(plan["inverse_links"]) == 1
    assert "c:belongs" not in plan["dependencies"]["c:owns"]
    assert "c:owns" not in plan["dependencies"]["c:belongs"]
    payload["resources"][-1]["spec"]["domain"] = {
        "mode": "ONE",
        "refs": [ref("c:person")],
    }
    blocked(payload, "INVERSE_ENDPOINTS")


def test_inverse_to_reuse_does_not_edit_existing_asset() -> None:
    payload = candidate()
    item = relation()
    item["spec"]["inverse_of"] = catalog_ref("asset:inverse")
    payload["resources"].append(item)
    assets = {
        "asset:inverse": {
            "id": 10,
            "revision": 2,
            "kind": "OBJECT_PROPERTY",
            "iri": "https://example.org/assets#inverse",
            "name": "inverse",
            "domain_iri": "https://example.org/business#Device",
            "range_iri": "https://example.org/business#Person",
        }
    }
    blocked(payload, "UNSUPPORTED", asset_catalog=assets)


@pytest.mark.parametrize(
    "kind,fields,datatype",
    [
        ("CARDINALITY", {"min": 1, "max": 2}, "integer"),
        (
            "NUMERIC_RANGE",
            {
                "minimum": "0",
                "maximum": "150",
                "minimum_inclusive": True,
                "maximum_inclusive": True,
            },
            "integer",
        ),
        ("PATTERN", {"regex": "^[A-Z]{1,20}$", "flags": "i"}, "string"),
        (
            "ENUM",
            {
                "allowed": [
                    {"datatype": "boolean", "lexical": "true"},
                    {"datatype": "boolean", "lexical": "false"},
                ]
            },
            "boolean",
        ),
    ],
)
def test_basic_constraints_compile_iri_paths(
    kind: str, fields: dict[str, Any], datatype: str
) -> None:
    payload = candidate()
    payload["resources"][2]["spec"]["datatype"] = datatype
    payload["constraints"] = [constraint(kind, path=path(), **fields)]
    plan = compile_payload(payload)
    assert plan["state"] == "COMPILED", plan["issues"]
    spec = plan["constraints"][0]["spec"]
    assert spec["path"] == {
        "iri": "https://example.org/business#Person/age",
        "inverse": False,
    }
    assert not any(key in json.dumps(spec) for key in ("candidate_id", "handle"))
    assert plan["dependencies"]["c:rule"] == ["c:age", "c:person"]


def test_class_membership_and_inverse_constraint_target() -> None:
    payload = candidate()
    payload["resources"].append(relation())
    payload["constraints"] = [
        constraint(
            "CLASS_MEMBERSHIP",
            path=path("c:owns"),
            allowed_class={"mode": "ONE", "refs": [ref("c:device")]},
        )
    ]
    plan = compile_payload(payload)
    assert plan["state"] == "COMPILED", plan["issues"]
    assert plan["constraints"][0]["spec"]["allowed_class"] == {
        "mode": "ONE",
        "iris": ["https://example.org/business#Device"],
    }
    payload["constraints"] = [
        constraint("CARDINALITY", path=path("c:owns", True), min=0, max=1)
    ]
    blocked(payload, "PATH_TARGET")
    payload["constraints"][0]["target_class"] = ref("c:device")
    assert compile_payload(payload)["state"] == "COMPILED"


@pytest.mark.parametrize(
    "kind,fields,reason",
    [
        ("CARDINALITY", {"min": 2, "max": 1}, "CARDINALITY_RANGE"),
        (
            "NUMERIC_RANGE",
            {
                "minimum": "2",
                "maximum": "1",
                "minimum_inclusive": True,
                "maximum_inclusive": True,
            },
            "NUMERIC_RANGE",
        ),
        (
            "NUMERIC_RANGE",
            {
                "minimum": "1",
                "maximum": "1",
                "minimum_inclusive": False,
                "maximum_inclusive": True,
            },
            "NUMERIC_RANGE",
        ),
        (
            "NUMERIC_RANGE",
            {
                "minimum": None,
                "maximum": None,
                "minimum_inclusive": True,
                "maximum_inclusive": True,
            },
            "EMPTY_NUMERIC_RANGE",
        ),
        ("PATTERN", {"regex": "[", "flags": ""}, "INVALID_PATTERN"),
        ("PATTERN", {"regex": "^(a+)+$", "flags": ""}, "UNSUPPORTED"),
        (
            "ENUM",
            {
                "allowed": [
                    {"datatype": "integer", "lexical": "1"},
                    {"datatype": "integer", "lexical": "+01"},
                ]
            },
            "DUPLICATE_ENUM_VALUE",
        ),
        (
            "ENUM",
            {"allowed": [{"datatype": "integer", "lexical": "1e2"}]},
            "INVALID_LEXICAL_VALUE",
        ),
    ],
)
def test_bad_constraints_fail_closed(
    kind: str, fields: dict[str, Any], reason: str
) -> None:
    payload = candidate()
    if kind == "PATTERN":
        payload["resources"][2]["spec"]["datatype"] = "string"
    payload["constraints"] = [constraint(kind, path=path(), **fields)]
    blocked(payload, reason)


def test_datatype_scope_feature_and_combined_cardinality_conflicts() -> None:
    payload = candidate()
    payload["constraints"] = [
        constraint("CARDINALITY", path=path(inverse=True), min=0, max=1)
    ]
    blocked(payload, "INVERSE_DATA_PATH")
    payload["constraints"] = [
        constraint(
            "ENUM", path=path(), allowed=[{"datatype": "boolean", "lexical": "yes"}]
        )
    ]
    blocked(payload, "INVALID_LEXICAL_VALUE")
    blocked(payload, "DATATYPE_MISMATCH")
    payload["resources"].append(relation())
    payload["resources"][-1]["spec"]["features"]["functional"] = True
    payload["constraints"] = [
        constraint("CARDINALITY", path=path("c:owns"), min=2, max=None)
    ]
    blocked(payload, "CARDINALITY_FEATURE_CONFLICT")
    payload["constraints"] = [
        constraint("CARDINALITY", path=path(), min=0, max=1),
        constraint("CARDINALITY", path=path(), min=2, max=3),
    ]
    payload["constraints"][1]["candidate_id"] = "c:ruleTwo"
    blocked(payload, "CARDINALITY_CONFLICT")
    payload["constraints"][1]["spec"] = copy.deepcopy(payload["constraints"][0]["spec"])
    blocked(payload, "DUPLICATE_CONSTRAINT")


@pytest.mark.parametrize("mode", ["ANY_OF", "ALL_OF"])
def test_complex_class_expressions_retained_but_unsupported(mode: str) -> None:
    payload = candidate()
    item = relation()
    item["spec"]["domain"] = {"mode": mode, "refs": [ref("c:person"), ref("c:device")]}
    payload["resources"].append(item)
    plan = blocked(payload, "UNSUPPORTED")
    assert any(i["state"] == "NOT_RUN" for i in plan["issues"])
    assert any(
        r["spec"].get("domain", {}).get("mode") == mode
        for r in plan["canonical_candidate"]["resources"]
    )


@pytest.mark.parametrize(
    "spec",
    [
        {"kind": "HAS_KEY", "class": ref("c:person"), "properties": [ref("c:age")]},
        {
            "kind": "PROPERTY_CHAIN",
            "chain": [ref("c:owns"), ref("c:owns")],
            "super": ref("c:owns"),
        },
    ],
)
def test_remaining_complex_axioms_explicitly_unsupported(spec: dict[str, Any]) -> None:
    payload = candidate()
    payload["resources"].append(relation())
    payload["axioms"] = [
        {"candidate_id": "c:axiom", "spec": spec, "evidence": evidence()}
    ]
    plan = blocked(payload, "UNSUPPORTED")
    assert plan["canonical_candidate"]["axioms"][0]["spec"] == spec


@pytest.mark.parametrize(
    "spec",
    [
        {"kind": "DATE_ORDER", "earlier": path(), "later": path(), "allow_equal": True},
        {"kind": "UNIQUE_TUPLE", "paths": [path()], "scope": "VALIDATION_DATASET"},
        {
            "kind": "CONDITIONAL_REQUIRED",
            "when_path": path(),
            "equals": {"datatype": "integer", "lexical": "1"},
            "require_any": [path()],
        },
    ],
)
def test_future_constraints_explicitly_unsupported(spec: dict[str, Any]) -> None:
    payload = candidate()
    payload["constraints"] = [
        constraint(spec["kind"], **{k: v for k, v in spec.items() if k != "kind"})
    ]
    blocked(payload, "UNSUPPORTED")


@pytest.mark.parametrize("feature", ["asymmetric", "reflexive", "irreflexive"])
def test_unsupported_features_not_silently_removed(feature: str) -> None:
    payload = candidate()
    item = relation()
    item["spec"]["features"][feature] = True
    payload["resources"].append(item)
    blocked(payload, "UNSUPPORTED")
    if feature == "asymmetric":
        item["spec"]["features"]["symmetric"] = True
        blocked(payload, "FEATURE_CONFLICT")


@pytest.mark.parametrize(
    "lexical,invalid", [("2023-02-29", True), ("2024-02-29", False)]
)
def test_business_date_lexical_is_checked_without_standards_claim(
    lexical: str, invalid: bool
) -> None:
    payload = candidate()
    payload["resources"][2]["spec"]["datatype"] = "date"
    payload["constraints"] = [
        constraint(
            "ENUM", path=path(), allowed=[{"datatype": "date", "lexical": lexical}]
        )
    ]
    if invalid:
        blocked(payload, "INVALID_LEXICAL_VALUE")
    else:
        plan = compile_payload(payload)
        assert plan["state"] == "COMPILED", plan["issues"]
        assert plan["constraints"][0]["spec"]["allowed"][0]["lexical"] == lexical


def test_context_profile_and_metadata_evidence() -> None:
    blocked(candidate(), "CONTEXT_MISMATCH", context_token="context:stale")
    blocked(candidate(), "PROFILE_MISMATCH", profile="STANDARD_DIGITALIZATION")
    payload = candidate()
    payload["profile_echo"] = "STANDARD_DIGITALIZATION"
    blocked(payload, "UNSUPPORTED", profile="STANDARD_DIGITALIZATION")
    payload = candidate()
    payload["ontology_metadata"] = {
        "metadata": metadata("测试本体"),
        "evidence": evidence(),
    }
    assert compile_payload(payload)["metadata"] == metadata("测试本体")
    payload["ontology_metadata"]["evidence"]["depends_on"] = ["c:fake"]
    blocked(payload, "UNKNOWN_DEPENDENCY")
    del payload["ontology_metadata"]["evidence"]
    with pytest.raises(CandidateParseError):
        parse_candidate_json(json.dumps(payload))


def test_nested_model_mutation_is_revalidated() -> None:
    model = OntologyCandidate.model_validate(candidate())
    model.resources[0].spec.__dict__["local_name"] = 123
    with pytest.raises(CandidateParseError):
        compile_candidate(
            model,
            namespace_catalog=NS,
            asset_catalog={},
            source_catalog=SOURCES,
            context_token="context:one",
        )


def test_multiple_inverses_for_same_resource_are_rejected() -> None:
    payload = candidate()
    payload["resources"] += [
        relation(inverse="c:belongs"),
        relation("c:belongs", reverse=True),
        relation("c:possesses", inverse="c:belongs"),
    ]
    blocked(payload, "INVERSE_CONFLICT")


def test_duplicate_reference_alias_and_catalog_scope_information() -> None:
    payload = candidate()
    payload["resources"][0]["spec"]["parents"] = [catalog_ref(), catalog_ref()]
    blocked(payload, "DUPLICATE_REFERENCE", asset_catalog=asset())
    payload = candidate()
    payload["resources"][0]["evidence"]["depends_on"] = ["c:device", "c:device"]
    blocked(payload, "DUPLICATE_EVIDENCE_REFERENCE")
    payload = candidate()
    payload["resources"][0]["spec"]["parents"] = [catalog_ref()]
    assets = asset()
    assets["asset:prop"] = {
        "id": 11,
        "revision": 2,
        "kind": "DATA_PROPERTY",
        "iri": "https://example.org/assets#ExistingPerson/id",
        "name": "ExistingPerson.id",
        "datatype": "string",
    }
    rule = constraint(
        "CARDINALITY",
        path={"property": catalog_ref("asset:prop"), "inverse": False},
        min=1,
        max=1,
    )
    payload["constraints"] = [rule]
    blocked(payload, "MISSING_PROPERTY_CONTEXT", asset_catalog=assets)
    assets["asset:prop"]["owner_iri"] = assets["asset:person"]["iri"]
    assert compile_payload(payload, asset_catalog=assets)["state"] == "COMPILED"
    assets["asset:alias"] = {**assets["asset:person"], "revision": 3}
    blocked(payload, "INVALID_CATALOG", asset_catalog=assets)


def test_large_pattern_repeat_and_malformed_uri_do_not_escape_as_exceptions() -> None:
    payload = candidate()
    payload["resources"][2]["spec"]["datatype"] = "string"
    payload["constraints"] = [
        constraint(
            "PATTERN", path=path(), regex="^a{999999999999999999999999}$", flags=""
        )
    ]
    blocked(payload, "INVALID_PATTERN")
    payload["resources"][2]["spec"]["datatype"] = "anyURI"
    payload["constraints"] = [
        constraint(
            "ENUM",
            path=path(),
            allowed=[{"datatype": "anyURI", "lexical": "http://[bad"}],
        )
    ]
    blocked(payload, "INVALID_LEXICAL_VALUE")


def test_emitted_pydantic_schema_is_closed_and_has_all_protocol_branches() -> None:
    schema = OntologyCandidate.model_json_schema(by_alias=True)
    assert schema["$id"] == "urn:knowledge:proposal:ontology-candidate:1.0"
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert OntologyCandidate.model_config["strict"] is True
    assert OntologyCandidate.model_config["extra"] == "forbid"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == "ontology-candidate/1.0"
    for name, definition in schema["$defs"].items():
        if definition.get("type") == "object":
            assert definition["additionalProperties"] is False, name
    assert {
        "NewClass",
        "NewDataProperty",
        "NewObjectProperty",
        "Reuse",
        "DateOrder",
        "UniqueTuple",
        "ConditionalRequired",
        "PropertyChain",
    } <= set(schema["$defs"])


def test_overlapping_variable_regex_repetitions_are_not_compiled() -> None:
    payload = candidate()
    payload["resources"][2]["spec"]["datatype"] = "string"
    payload["constraints"] = [
        constraint("PATTERN", path=path(), regex="^a{0,1000}a{0,1000}$", flags="")
    ]
    blocked(payload, "UNSUPPORTED")


def test_numeric_intersections_and_integer_empty_interval_are_rejected() -> None:
    payload = candidate()
    payload["constraints"] = [
        constraint(
            "NUMERIC_RANGE",
            path=path(),
            minimum="10",
            maximum=None,
            minimum_inclusive=True,
            maximum_inclusive=True,
        ),
        constraint(
            "NUMERIC_RANGE",
            path=path(),
            minimum=None,
            maximum="5",
            minimum_inclusive=True,
            maximum_inclusive=True,
        ),
    ]
    payload["constraints"][1]["candidate_id"] = "c:other"
    blocked(payload, "NUMERIC_RANGE_CONFLICT")
    payload["constraints"] = [
        constraint(
            "NUMERIC_RANGE",
            path=path(),
            minimum="1",
            maximum="2",
            minimum_inclusive=False,
            maximum_inclusive=False,
        )
    ]
    blocked(payload, "NUMERIC_RANGE_CONFLICT")
    payload["resources"][2]["spec"]["datatype"] = "decimal"
    assert compile_payload(payload)["state"] == "COMPILED"


def axiom(cid: str, kind: str, **fields: Any) -> dict[str, Any]:
    return {
        "candidate_id": cid,
        "spec": {"kind": kind, **fields},
        "evidence": evidence(),
    }


@pytest.mark.parametrize("kind", ["EQUIVALENT_CLASSES", "DISJOINT_CLASSES"])
def test_named_class_axioms_compile_only_catalog_or_candidate_iris(kind: str) -> None:
    payload = candidate()
    payload["axioms"] = [
        axiom(
            "c:axiom", kind, classes=[catalog_ref(), ref("c:person"), ref("c:device")]
        )
    ]
    assets = asset()
    plan = compile_payload(payload, asset_catalog=assets)
    assert plan["compiler_version"] == "ontology-plan/1.1"
    assert plan["state"] == "COMPILED", plan["issues"]
    assert plan["axioms"] == [
        {
            "candidate_id": "c:axiom",
            "kind": kind,
            "iris": sorted(
                [
                    assets["asset:person"]["iri"],
                    "https://example.org/business#Person",
                    "https://example.org/business#Device",
                ]
            ),
        }
    ]
    assert plan["dependencies"]["c:axiom"] == ["c:device", "c:person"]
    payload["axioms"][0]["spec"]["classes"].reverse()
    reversed_plan = compile_payload(payload, asset_catalog=assets)
    assert reversed_plan["axioms"] == plan["axioms"]
    # Evidence and candidate AST order still belong to the content fingerprint.
    assert reversed_plan["digest"] != plan["digest"]


@pytest.mark.parametrize("kind", ["EQUIVALENT_CLASSES", "DISJOINT_CLASSES"])
def test_class_axioms_wrong_kind_unknown_and_duplicate_references(kind: str) -> None:
    payload = candidate()
    payload["axioms"] = [
        axiom("c:axiom", kind, classes=[ref("c:person"), ref("c:age")])
    ]
    blocked(payload, "REFERENCE_KIND")
    payload["axioms"][0]["spec"]["classes"] = [
        ref("c:person"),
        catalog_ref("asset:fake"),
    ]
    blocked(payload, "UNKNOWN_REFERENCE")
    payload["axioms"][0]["spec"]["classes"] = [ref("c:person"), ref("c:person")]
    blocked(payload, "DUPLICATE_REFERENCE")


@pytest.mark.parametrize("object_property", [False, True])
def test_subproperty_same_kind_refs_and_legal_cycles(object_property: bool) -> None:
    payload = candidate()
    if object_property:
        payload["resources"] += [relation("c:propOne"), relation("c:propTwo")]
    else:
        payload["resources"] += [data_property("c:propOne"), data_property("c:propTwo")]
    payload["axioms"] = [
        axiom("c:subOne", "SUBPROPERTY", sub=ref("c:propOne"), super=ref("c:propTwo")),
        axiom("c:subTwo", "SUBPROPERTY", sub=ref("c:propTwo"), super=ref("c:propOne")),
    ]
    plan = compile_payload(payload)
    assert plan["state"] == "COMPILED", plan["issues"]
    assert len(plan["axioms"]) == 2
    iris = {r["candidate_id"]: r["iri"] for r in plan["resources"]}
    assert plan["axioms"][0] == {
        "candidate_id": "c:subOne",
        "kind": "SUBPROPERTY",
        "sub_iri": iris["c:propOne"],
        "super_iri": iris["c:propTwo"],
    }
    payload["axioms"][0]["spec"]["super"] = ref("c:propOne")
    blocked(payload, "INVALID_AXIOM")


def test_subproperty_wrong_kind_and_pinned_reuse_property() -> None:
    payload = candidate()
    payload["resources"].append(relation())
    payload["axioms"] = [
        axiom("c:sub", "SUBPROPERTY", sub=ref("c:age"), super=ref("c:owns"))
    ]
    blocked(payload, "REFERENCE_KIND")
    payload["axioms"][0]["spec"]["super"] = ref("c:person")
    blocked(payload, "REFERENCE_KIND")
    assets = {
        "asset:data": {
            "id": 2,
            "revision": 1,
            "kind": "DATA_PROPERTY",
            "iri": "https://example.org/assets#SomeType/age",
            "name": "SomeType.age",
        }
    }
    payload["axioms"][0]["spec"]["super"] = catalog_ref("asset:data")
    plan = compile_payload(payload, asset_catalog=assets)
    assert plan["state"] == "COMPILED", plan["issues"]
    assert plan["axioms"][0]["super_iri"] == assets["asset:data"]["iri"]


def test_axiom_deduplication_and_equivalence_disjoint_conflict() -> None:
    payload = candidate()
    payload["resources"].append(new_class("c:other", "Other", "其他"))
    payload["axioms"] = [
        axiom(
            "c:eqOne", "EQUIVALENT_CLASSES", classes=[ref("c:person"), ref("c:device")]
        ),
        axiom(
            "c:eqTwo", "EQUIVALENT_CLASSES", classes=[ref("c:device"), ref("c:person")]
        ),
    ]
    blocked(payload, "DUPLICATE_AXIOM")
    payload["axioms"][1]["spec"]["classes"] = [ref("c:device"), ref("c:other")]
    payload["axioms"].append(
        axiom(
            "c:disjoint", "DISJOINT_CLASSES", classes=[ref("c:person"), ref("c:other")]
        )
    )
    blocked(payload, "AXIOM_CONFLICT")
    payload["axioms"].pop()
    plan = compile_payload(payload)
    assert plan["state"] == "COMPILED"
    payload["axioms"][0]["evidence"]["depends_on"] = ["c:eqTwo"]
    payload["axioms"][1]["evidence"]["depends_on"] = ["c:eqOne"]
    blocked(payload, "DEPENDENCY_CYCLE")


@pytest.mark.parametrize(
    "lexical",
    ["2024-02-30", "2024-2-9", "2024-02-29T00:00:00", "2024-02-29Z", "0000-01-01"],
)
def test_business_date_rejects_noncalendar_and_noncanonical_lexical(
    lexical: str,
) -> None:
    payload = candidate()
    payload["resources"][2]["spec"]["datatype"] = "date"
    payload["constraints"] = [
        constraint(
            "ENUM", path=path(), allowed=[{"datatype": "date", "lexical": lexical}]
        )
    ]
    blocked(payload, "INVALID_LEXICAL_VALUE")


def test_issue_and_parse_codes_are_exported_for_translation() -> None:
    payload = candidate()
    payload["resources"][0]["spec"]["parents"] = [ref("c:missing")]
    plan = compile_payload(payload)
    assert all(CandidateErrorCode(i["code"]) for i in plan["issues"])
    assert CandidateErrorCode.UNSUPPORTED.value == "KG.CANDIDATE_UNSUPPORTED"
    with pytest.raises(CandidateParseError) as exc:
        parse_candidate_json("[]")
    assert CandidateErrorCode(exc.value.code) == CandidateErrorCode.INVALID_STRUCTURE
