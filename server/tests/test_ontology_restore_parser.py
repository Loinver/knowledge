"""PC09 restore: serializer round trips and fail-closed, database-free parsing."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import cast

import pytest
from app.core.errors import KGError
from app.models.enums import ResourceKind
from app.schemas.ontology import OntologyExportFormat
from app.schemas.ontology_import import ImportFormat
from app.semantics.ontology_rdf import (
    OntologyRdfMetadata,
    OntologyRdfResource,
    serialize_ontology_rdf,
)
from app.semantics.ontology_restore import RestoreDocument, parse_restore_document
from rdflib import OWL, RDF, RDFS, SH, XSD, Graph, Literal, Namespace, URIRef
from rdflib.term import Node

EX = Namespace("https://example.org/kg#")
KG = Namespace("urn:knowledge:semantics:")
REF = Namespace("urn:knowledge:ref:")
ROOT = URIRef("https://example.org/ontology/hr")
SALARY = URIRef(f"{EX.Employee}/salary")
STATUS = URIRef(f"{EX.Employee}/status")
ENUM = URIRef("urn:knowledge:enum:7:r2")
SALARY_SHAPE = URIRef(f"{SALARY}#shape")
STATUS_SHAPE = URIRef(f"{STATUS}#shape")


@pytest.fixture()
def snapshots() -> dict[int, OntologyRdfResource]:
    def resource(
        name: str, kind: ResourceKind = ResourceKind.ENTITY, **extra: object
    ) -> OntologyRdfResource:
        return OntologyRdfResource.model_validate(
            {
                "name": name,
                "iri": f"{EX}{name}",
                "kind": kind,
                "namespace": {"prefix": "ex", "iri": str(EX)},
                "parent_ids": [],
                "resource_refs": [],
                "label_i18n": {"zh-CN": "名称", "en-US": name},
                "definition_i18n": {"zh-CN": "定义", "en-US": "Definition"},
                **extra,
            }
        )

    def reference(role: str, target_id: int) -> dict[str, object]:
        return {"role": role, "target_id": target_id}

    def relation_detail() -> dict[str, object]:
        return {
            "domain_cardinality": {
                "min": 1,
                "max": 2,
                "role_label_i18n": {"zh-CN": "雇员"},
            },
            "range_cardinality": {"min": 0, "max": -1, "role_label_i18n": None},
            "domain_role_i18n": {"zh-CN": "员工", "en-US": "Employee"},
            "range_role_i18n": None,
            "owl": {
                "functional": False,
                "inverse_functional": True,
                "symmetric": False,
                "transitive": True,
            },
        }

    common: dict[str, object] = {
        "min_cardinality": 1,
        "max_cardinality": 2,
        "min_value": None,
        "max_value": None,
        "nullable": False,
    }
    return {
        1: resource("Person"),
        2: resource(
            "Employee",
            parent_ids=[1],
            resource_refs=[reference("data_prop", 4), reference("data_prop", 5)],
            datatype_props=[
                {
                    **common,
                    "name": "salary",
                    "iri": str(SALARY),
                    "datatype": "decimal",
                    "min_value": "0",
                    "max_value": "100.50",
                    "default_value": "0",
                    "source_clause_ref": "example 1.2",
                },
                {
                    **common,
                    "name": "status",
                    "iri": str(STATUS),
                    "datatype": "enum",
                    "default_value": "OPEN",
                    "enum_dict_id": 7,
                    "enum_dict_revision": 2,
                    "enum_dictionary": {
                        "id": 7,
                        "revision": 2,
                        "name": "EmploymentStatus",
                        "label_i18n": {"zh-CN": "状态", "en-US": "Status"},
                        "definition_i18n": {
                            "zh-CN": "状态定义",
                            "en-US": "Status definition",
                        },
                        "entries": [
                            {
                                "value": "OPEN",
                                "label_i18n": {"zh-CN": "开放", "en-US": "Open"},
                            },
                            {
                                "value": "CLOSED",
                                "label_i18n": {"zh-CN": "关闭", "en-US": "Closed"},
                            },
                        ],
                    },
                },
            ],
        ),
        3: resource("Department"),
        4: resource("Employee.salary", ResourceKind.DATATYPE_PROP, iri=str(SALARY)),
        5: resource("Employee.status", ResourceKind.DATATYPE_PROP, iri=str(STATUS)),
        6: resource(
            "WorksFor",
            ResourceKind.OBJECT_PROP,
            resource_refs=[
                reference("relation_domain", 2),
                reference("relation_range", 3),
                reference("inverse_of", 7),
                reference("assoc_resource", 8),
            ],
            object_prop=relation_detail(),
        ),
        7: resource(
            "Employs",
            ResourceKind.OBJECT_PROP,
            resource_refs=[
                reference("relation_domain", 3),
                reference("relation_range", 2),
            ],
            object_prop=relation_detail(),
        ),
        8: resource(
            "WorksForAssociation",
            ResourceKind.ASSOC,
            resource_refs=[reference("assoc_attribute", 9)],
            datatype_props=[
                {
                    **common,
                    "name": "note",
                    "iri": f"{EX.WorksForAssociation}/note",
                    "datatype": "string",
                }
            ],
        ),
        9: resource(
            "WorksForAssociation.note",
            ResourceKind.DATATYPE_PROP,
            iri=f"{EX.WorksForAssociation}/note",
        ),
    }


def serialize(
    snapshots: dict[int, OntologyRdfResource], rdf_format: ImportFormat = "turtle"
) -> str:
    return serialize_ontology_rdf(
        OntologyRdfMetadata(
            name="HumanResources",
            iri=str(ROOT),
            label_i18n={"zh-CN": "人事", "en-US": "HR"},
            definition_i18n={"zh-CN": "人事定义"},
        ),
        snapshots,
        revision=6,
        rdf_format=OntologyExportFormat(rdf_format),
    )


@pytest.fixture()
def graph(snapshots: dict[int, OntologyRdfResource]) -> Graph:
    return Graph().parse(data=serialize(snapshots), format="turtle")


def parse(graph: Graph, rdf_format: ImportFormat = "turtle") -> RestoreDocument:
    return parse_restore_document(rdf_format, graph.serialize(format=rdf_format))


def reasons(document: RestoreDocument) -> set[object]:
    return {issue.params.get("reason", issue.code) for issue in document.issues}


@pytest.mark.parametrize("rdf_format", ["turtle", "json-ld"])
def test_real_serializer_round_trip(
    snapshots: dict[int, OntologyRdfResource], rdf_format: ImportFormat
) -> None:
    document = parse_restore_document(rdf_format, serialize(snapshots, rdf_format))
    assert document.issues == []
    assert document.unsupported_triples == []
    assert document.source_revision == 6
    assert document.metadata is not None and document.metadata.name == "HumanResources"
    assert len(document.resources) == len(snapshots)
    resources = {item.iri: item for item in document.resources}
    assert resources[str(EX.Employee)].parent_iris == [str(EX.Person)]
    assert resources[str(EX.WorksForAssociation)].kind == ResourceKind.ASSOC
    salary = resources[str(SALARY)].datatype
    assert salary is not None
    assert salary.name == "salary"
    assert salary.datatype == "decimal"
    assert salary.nullable is False
    assert salary.default_value == "0"
    assert (salary.min_cardinality, salary.max_cardinality) == (1, 2)
    assert Decimal(salary.min_value or "NaN") == 0
    assert Decimal(salary.max_value or "NaN") == Decimal("100.5")
    assert salary.source_clause_ref == "example 1.2"
    status = resources[str(STATUS)]
    assert status.enum_iri == str(ENUM)
    assert status.datatype is not None
    assert (status.datatype.enum_dict_id, status.datatype.enum_dict_revision) == (7, 2)
    dictionary = document.enums[0]
    assert dictionary.source_revision == 2
    assert dictionary.definition.name == "EmploymentStatus"
    assert [entry.value for entry in dictionary.definition.entries] == [
        "OPEN",
        "CLOSED",
    ]
    assert dictionary.definition.entries[1].label_i18n["zh-CN"] == "关闭"
    relation = resources[str(EX.WorksFor)]
    assert relation.object_prop == snapshots[6].object_prop
    assert {ref.role for ref in relation.refs} == {
        "relation_domain",
        "relation_range",
        "inverse_of",
        "assoc_resource",
    }


@pytest.mark.parametrize("rdf_format", ["turtle", "json-ld"])
@pytest.mark.parametrize("role", ["union_of", "intersection_of"])
def test_unexportable_roles_remain_unsupported(
    graph: Graph, rdf_format: ImportFormat, role: str
) -> None:
    graph.add((EX.WorksFor, REF[role], EX.Employs))
    document = parse(graph, rdf_format)
    assert "UNSUPPORTED_TRIPLES" in reasons(document)
    assert any(str(REF[role]) in triple for triple in document.unsupported_triples)
    assert all(ref.role != role for item in document.resources for ref in item.refs)


def test_relation_shapes_follow_paths_without_database_ids(graph: Graph) -> None:
    for index, old in enumerate(list(graph.objects(EX.Employee, SH.property))):
        if "relation-shape" not in str(old):
            continue
        replacement = URIRef(f"urn:shape:unrelated-{index}")
        for subject, predicate, obj in list(graph.triples((old, None, None))):
            graph.remove((subject, predicate, obj))
            graph.add((replacement, predicate, obj))
        graph.remove((EX.Employee, SH.property, old))
        graph.add((EX.Employee, SH.property, replacement))
    assert parse(graph).issues == []


@pytest.mark.parametrize(
    ("subject", "predicate", "value", "reason"),
    [
        (EX.Employee, KG.name, Literal("Other"), "field_cardinality"),
        (EX.Employee, RDFS.label, Literal("重复", lang="zh-CN"), "duplicate_language"),
        (
            EX.Employee,
            RDFS.label,
            Literal("Deutsch", lang="de"),
            "unsupported_language",
        ),
        (
            EX.Employee,
            RDFS.comment,
            URIRef("urn:not-a-literal"),
            "unsupported_language",
        ),
        (EX.Employee, RDF.type, OWL.ObjectProperty, "resource_type_cardinality"),
        (EX.Employee, RDFS.subClassOf, EX.Missing, "incomplete_resource_closure"),
        (EX.Person, RDFS.subClassOf, EX.Employee, "cyclic_parent_hierarchy"),
        (EX.WorksFor, RDFS.domain, EX.Person, "conflicting_reference"),
        (EX.WorksFor, REF.relation_domain, EX.Person, "reference_cardinality"),
        (EX.WorksFor, REF.assoc_resource, EX.Employee, "reference_cardinality"),
        (SALARY, RDFS.domain, EX.Person, "conflicting_property_owner"),
        (SALARY_SHAPE, SH.path, STATUS, "field_cardinality"),
        (SALARY_SHAPE, SH.minCount, Literal(3), "field_cardinality"),
        (
            URIRef(f"{STATUS}#enum-list-0"),
            RDF.first,
            Literal("NEW"),
            "field_cardinality",
        ),
    ],
)
def test_conflicting_multivalued_fields_block(
    graph: Graph, subject: URIRef, predicate: URIRef, value: Node, reason: str
) -> None:
    graph.add((subject, predicate, value))
    assert reason in reasons(parse(graph))


@pytest.mark.parametrize(
    ("subject", "predicate", "value", "reason"),
    [
        (
            EX.Employee,
            KG.resourceKind,
            Literal("OBJECT_PROP"),
            "conflicting_resource_kind",
        ),
        (EX.Employee, KG.resourceKind, URIRef("urn:ENTITY"), "expected_string"),
        (SALARY, KG.nullable, Literal("false"), "expected_boolean"),
        (
            SALARY,
            KG.constraintsRecorded,
            Literal(False),
            "incomplete_constraint_snapshot",
        ),
        (SALARY_SHAPE, SH.datatype, XSD.string, "conflicting_datatype"),
        (SALARY_SHAPE, SH.maxCount, Literal(0), "invalid_cardinality_bounds"),
        (SALARY_SHAPE, SH.maxCount, Literal(True), "expected_nonnegative_integer"),
        (
            SALARY_SHAPE,
            SH.minInclusive,
            Literal("101", datatype=XSD.decimal),
            "invalid_numeric_bounds",
        ),
        (SALARY_SHAPE, SH.defaultValue, Literal("9"), "conflicting_default"),
        (EX.WorksFor, KG.domainCardinality, Literal("[]"), "invalid_json_object"),
        (
            EX.WorksFor,
            KG.domainCardinality,
            Literal('{"min":true,"max":2}'),
            "invalid_json_cardinality",
        ),
        (
            EX.WorksFor,
            KG.domainCardinality,
            Literal('{"min":0,"max":null}'),
            "invalid_json_cardinality",
        ),
        (
            EX.WorksFor,
            KG.domainCardinality,
            Literal('{"min":0}'),
            "invalid_json_cardinality",
        ),
        (
            EX.WorksFor,
            KG.domainCardinality,
            Literal('{"min":0,"max":-1,"other":1}'),
            "invalid_json_cardinality",
        ),
        (
            EX.WorksFor,
            KG.domainCardinality,
            Literal('{"min":1,"min":2,"max":2}'),
            "invalid_json_object",
        ),
        (
            EX.WorksFor,
            KG.domainCardinality,
            Literal('{"min":NaN,"max":2}'),
            "invalid_json_object",
        ),
        (
            EX.WorksFor,
            KG.domainCardinality,
            Literal('{"min":0,"max":2}'),
            "cardinality_shape_mismatch",
        ),
        (
            EX.WorksFor,
            KG.domainRole,
            Literal('{"fr":"employee"}'),
            "invalid_json_labels",
        ),
        (
            EX.WorksFor,
            KG.owlFeatures,
            Literal('{"functional":"false"}'),
            "invalid_owl_features",
        ),
        (
            EX.WorksFor,
            KG.owlFeatures,
            Literal('{"transitive":false}'),
            "owl_feature_mismatch",
        ),
        (ENUM, KG.revision, Literal(9), "enum_revision_mismatch"),
        (
            URIRef(f"{STATUS}#enum-list-0"),
            RDF.first,
            Literal("UNKNOWN"),
            "enum_list_mismatch",
        ),
        (
            URIRef(f"{STATUS}#enum-list-0"),
            RDF.rest,
            URIRef(f"{STATUS}#enum-list-0"),
            "invalid_enum_list",
        ),
        (URIRef(f"{ENUM}#entry-1"), KG.value, Literal("OPEN"), "duplicate_enum_value"),
        (
            URIRef(f"{STATUS}#enum-list-1"),
            RDF.first,
            Literal("OPEN"),
            "empty_or_duplicate_enum_list",
        ),
    ],
)
def test_invalid_values_block(
    graph: Graph, subject: URIRef, predicate: URIRef, value: Node, reason: str
) -> None:
    graph.set((subject, predicate, value))
    assert reason in reasons(parse(graph))


@pytest.mark.parametrize("predicate", [KG.name, RDFS.comment, RDFS.label])
def test_legacy_enum_does_not_invent_dictionary_history(
    graph: Graph, predicate: URIRef
) -> None:
    graph.remove((ENUM, predicate, None))
    document = parse(graph)
    assert "invalid_or_missing_enum_definition" in reasons(document)
    assert document.enums == []
    prop = next(item for item in document.resources if item.iri == str(STATUS))
    assert prop.datatype is not None and prop.datatype.enum_dict_revision == 2


def test_extra_and_rule_triples_remain_unconsumed(graph: Graph) -> None:
    extra = (EX.Employee, URIRef("urn:extra:predicate"), Literal("extra"))
    rule = (EX.Employee, SH.rule, URIRef("urn:rule:unknown"))
    graph.add(extra)
    graph.add(rule)
    document = parse(graph)
    assert set(document.unsupported_triples) == {
        " ".join(node.n3() for node in triple) + " ." for triple in (extra, rule)
    }
    assert "UNSUPPORTED_TRIPLES" in reasons(document)
    assert document.triple_count == len(graph)


def test_duplicate_shapes_block_even_if_their_constraints_match(graph: Graph) -> None:
    duplicate = URIRef("urn:shape:duplicate")
    for _, predicate, value in list(graph.triples((SALARY_SHAPE, None, None))):
        graph.add((duplicate, predicate, value))
    graph.add((EX.Employee, SH.property, duplicate))
    assert "duplicate_property_shape" in reasons(parse(graph))


def test_external_supported_subset_and_missing_root_metadata() -> None:
    content = """@prefix ex: <https://example.org/kg#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ex:Employee a owl:Class; rdfs:label "Employee"@en ."""
    document = parse_restore_document("turtle", content)
    assert document.metadata is None
    assert document.resources[0].name == "Employee"
    assert document.resources[0].label_i18n == {"en-US": "Employee"}
    assert document.unsupported_triples == []
    assert reasons(document) == {"ontology_root_cardinality"}


def test_multiple_roots_and_bad_property_iri_block(graph: Graph) -> None:
    graph.add((URIRef("urn:ontology:second"), RDF.type, OWL.Ontology))
    graph.set((SALARY, KG.propertyName, Literal("other")))
    document = parse(graph)
    assert document.metadata is None
    assert "ontology_root_cardinality" in reasons(document)
    assert "property_iri_mismatch" in reasons(document)


def test_legacy_resource_name_and_property_name_remain_distinct(graph: Graph) -> None:
    graph.set((SALARY, KG.name, Literal("Salary")))
    graph.set((SALARY, KG.propertyName, Literal("salary")))
    document = parse(graph)
    resource = next(item for item in document.resources if item.iri == str(SALARY))
    assert resource.name == "Salary"
    assert resource.datatype is not None and resource.datatype.name == "salary"
    assert document.issues == []


@pytest.mark.parametrize(
    ("rdf_format", "content", "reason"),
    [
        (
            "json-ld",
            '{"@context":"https://example.org/remote.jsonld"}',
            "external_json_ld_context",
        ),
        (
            "json-ld",
            '{"@context":{"@import":"file:///tmp/private.jsonld"}}',
            "external_json_ld_context",
        ),
        (
            "turtle",
            "<urn:o> <http://www.w3.org/2002/07/owl#imports> "
            "<https://example.org/import> .",
            "owl_imports_not_allowed",
        ),
        ("turtle", "not rdf", "invalid_rdf"),
        ("turtle", " " * 65537, "import_too_large"),
        (
            "turtle",
            "\n".join(f'<urn:s:{i}> <urn:p> "v" .' for i in range(2001)),
            "too_many_triples",
        ),
    ],
)
def test_parser_reuses_offline_and_size_guards(
    monkeypatch: pytest.MonkeyPatch, rdf_format: ImportFormat, content: str, reason: str
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        pytest.fail("RDF restore attempted network access")

    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    with pytest.raises(KGError) as error:
        parse_restore_document(rdf_format, content)
    assert error.value.params["reason"] == reason


def test_jsonld_and_turtle_produce_same_document(
    snapshots: dict[int, OntologyRdfResource],
) -> None:
    turtle = parse_restore_document("turtle", serialize(snapshots, "turtle"))
    jsonld = parse_restore_document("json-ld", serialize(snapshots, "json-ld"))
    assert turtle.model_dump() == jsonld.model_dump()
    assert json.loads(jsonld.model_dump_json())["source_revision"] == 6


@pytest.mark.parametrize("predicate", [KG.nullable, KG.constraintsRecorded])
def test_missing_native_property_metadata_blocks(
    graph: Graph, predicate: URIRef
) -> None:
    graph.remove((SALARY, predicate, None))
    document = parse(graph)
    assert any(
        issue.params.get("predicate") == str(predicate) for issue in document.issues
    )


def test_enum_schema_cannot_silently_trim_source_values(graph: Graph) -> None:
    graph.set((ENUM, KG.name, Literal(" EmploymentStatus ")))
    document = parse(graph)
    assert "enum_definition_normalization" in reasons(document)
    assert document.enums == []


def test_external_property_subset_preserves_owner_and_name() -> None:
    content = """@prefix ex: <https://example.org/kg#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        ex:Employee a owl:Class .
        <https://example.org/kg#Employee/title> a owl:DatatypeProperty;
            rdfs:domain ex:Employee; rdfs:range xsd:string ."""
    document = parse_restore_document("turtle", content)
    assert reasons(document) == {"ontology_root_cardinality"}
    assert document.unsupported_triples == []
    prop = next(item for item in document.resources if item.datatype is not None)
    assert prop.name == "Employee.title"
    assert prop.namespace_iri == str(EX)
    assert prop.datatype is not None and prop.datatype.name == "title"


def test_jsonld_named_graph_is_not_silently_discarded(graph: Graph) -> None:
    content = json.loads(graph.serialize(format="json-ld"))
    content.append(
        {
            "@id": "urn:hidden:graph",
            "@graph": [{"@id": "urn:subject", "urn:predicate": [{"@value": "hidden"}]}],
        }
    )
    document = parse_restore_document("json-ld", json.dumps(content))
    assert "named_graph_not_supported" in reasons(document)
    assert document.triple_count == len(graph) + 1
    assert document.unsupported_triples == [
        '<urn:subject> <urn:predicate> "hidden" <urn:hidden:graph> .'
    ]


@pytest.mark.parametrize("imports", [False, True])
def test_jsonld_named_graph_cannot_bypass_existing_guards(imports: bool) -> None:
    statement = {
        "@id": "urn:o",
        str(OWL.imports): [{"@id": "https://example.org/import"}],
    }
    entries = (
        [statement]
        if imports
        else [{"@id": f"u:{index}", "p": 1} for index in range(2001)]
    )
    content = json.dumps(
        {
            "@context": {"p": "urn:predicate"},
            "@id": "urn:hidden:graph",
            "@graph": entries,
        },
        separators=(",", ":"),
    )
    assert len(content.encode()) < 65536
    expected = "owl_imports_not_allowed" if imports else "too_many_triples"
    with pytest.raises(KGError) as caught:
        parse_restore_document("json-ld", content)
    assert caught.value.params["reason"] == expected


def test_invalid_boolean_lexical_form_blocks(graph: Graph) -> None:
    graph.remove((SALARY, KG.nullable, None))
    content = (
        graph.serialize(format="turtle")
        + f'\n<{SALARY}> <{KG.nullable}> "maybe"^^<{XSD.boolean}> .'
    )
    with pytest.warns(UserWarning, match="weird boolean"):
        document = parse_restore_document("turtle", content)
    assert "expected_boolean" in reasons(document)


@pytest.mark.parametrize(
    "datatype", ["string", "integer", "decimal", "boolean", "date"]
)
def test_all_supported_scalar_datatypes(
    snapshots: dict[int, OntologyRdfResource], datatype: str
) -> None:
    detail = snapshots[2].datatype_props[0]
    detail.update(
        {
            "datatype": datatype,
            "min_value": None,
            "max_value": None,
            "nullable": True,
            "min_cardinality": None,
            "max_cardinality": None,
            "default_value": None,
        }
    )
    document = parse_restore_document("turtle", serialize(snapshots))
    assert document.issues == []
    prop = next(item for item in document.resources if item.iri == str(SALARY))
    assert prop.datatype is not None
    assert prop.datatype.datatype == datatype
    assert prop.datatype.nullable is True
    assert prop.datatype.min_cardinality is None


@pytest.mark.parametrize("rdf_format", ["turtle", "json-ld"])
def test_serializer_rule_snapshots_block_restore(
    snapshots: dict[int, OntologyRdfResource], rdf_format: ImportFormat
) -> None:
    content = serialize_ontology_rdf(
        OntologyRdfMetadata(
            name="Rules", iri=str(ROOT), label_i18n=None, definition_i18n=None
        ),
        snapshots,
        revision=1,
        rdf_format=OntologyExportFormat(rdf_format),
        rules=[
            {
                "identifier": "R01",
                "target_iri": str(EX.Employee),
                "body": {"kind": "EXTERNAL"},
            }
        ],
    )
    document = parse_restore_document(rdf_format, content)
    assert len(document.unsupported_triples) == 1
    assert str(KG.ruleSnapshot) in document.unsupported_triples[0]
    assert reasons(document) == {"UNSUPPORTED_TRIPLES"}


def test_format_is_enforced_at_runtime() -> None:
    with pytest.raises(KGError) as caught:
        parse_restore_document(cast(ImportFormat, "xml"), "")
    assert caught.value.params["reason"] == "unsupported_import_format"


def test_oversized_integer_literal_reports_an_issue(graph: Graph) -> None:
    graph.set((ROOT, OWL.versionInfo, Literal("9" * 5000)))
    assert "integer_out_of_range" in reasons(parse(graph))
