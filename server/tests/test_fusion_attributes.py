"""PC16: deterministic policy, frozen explanations, isolation and pointer safety."""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path

import pytest
from app.core.db import Base
from app.core.errors import KGError
from app.domain.ai_suggestion_service import apply_suggestion
from app.domain.evidence_service import trace_entity_evidence, trace_entity_fusion
from app.domain.extraction_service import get_current_graph, start_run
from app.domain.fusion_policy import resolve_attribute, validate_fusion_policies
from app.domain.mapping_compiler import compile_mapping
from app.domain.mapping_service import (
    create_mapping,
    get_draft_revision,
    publish_mapping,
    save_draft,
)
from app.domain.metadata_service import capture_metadata
from app.domain.source_service import create_datasource
from app.models.data_access import MappingRevision
from app.models.domain import Ontology, OntologyRevision
from app.models.extraction import (
    EntityIdentity,
    ExtractionRun,
    GraphRevision,
    GraphTriple,
)
from app.models.governance import AiSuggestion
from app.schemas.datasource import DatasourceCreate
from app.schemas.extraction import EntityFusionOut
from app.schemas.mapping import MappingCreate, MappingRevisionCreate
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session


def policy(rank: int = 1, null: str = "IGNORE", conflict: str = "PRIORITY") -> dict:
    return {"priority": rank, "null_policy": null, "conflict_policy": conflict}


def candidate(value: object, rank: int = 1, table: str = "a", key: str = "1") -> dict:
    return {
        "source_id": 1,
        "schema_name": "main",
        "table_name": table,
        "row_key": key,
        "column": "name",
        "priority": rank,
        "value": value,
        "input_value": value,
        "state": "NULL" if value is None else "VALUE",
    }


@pytest.mark.parametrize(
    ("values", "config", "reason", "value", "state"),
    [
        (
            [candidate("A"), candidate("B", 2, "b")],
            policy(),
            "SOURCE_PRIORITY",
            "A",
            "RESOLVED",
        ),
        (
            [candidate("A"), candidate("A", 2, "b")],
            policy(),
            "AGREEMENT",
            "A",
            "RESOLVED",
        ),
        (
            [candidate(None), candidate("B", 2, "b")],
            policy(),
            "SINGLE_VALUE",
            "B",
            "RESOLVED",
        ),
        (
            [candidate(None), candidate("B", 2, "b")],
            policy(null="KEEP"),
            "SOURCE_PRIORITY",
            None,
            "RESOLVED",
        ),
        (
            [candidate(None), candidate(None, 2, "b")],
            policy(),
            "ALL_NULL",
            None,
            "RESOLVED",
        ),
        (
            [candidate("A"), candidate("B", 1, "b")],
            policy(),
            "PRIORITY_TIE",
            None,
            "QUARANTINED",
        ),
        (
            [candidate("A"), candidate("B", 2, "b")],
            policy(conflict="QUARANTINE"),
            "CONFLICT_QUARANTINED",
            None,
            "QUARANTINED",
        ),
        (
            [candidate("A"), candidate("B")],
            policy(),
            "DUPLICATE_SOURCE_CONFLICT",
            None,
            "QUARANTINED",
        ),
    ],
)
def test_order_independent_decisions(
    values: list[dict], config: dict, reason: str, value: object, state: str
) -> None:
    result = resolve_attribute("name", values, config)
    assert result == resolve_attribute("name", values[::-1], config)
    assert (result["reason"], result["final_value"], result["state"]) == (
        reason,
        value,
        state,
    )


def test_identical_duplicates_do_not_vote() -> None:
    result = resolve_attribute(
        "name", [candidate("A"), candidate("A"), candidate("B", 2, "b")], policy()
    )
    assert result["reason"] == "SOURCE_PRIORITY"
    assert result["candidates"][0]["occurrences"] == 2
    assert len(result["candidates"]) == 2


def test_equivalent_transforms_preserve_distinct_inputs_in_either_order() -> None:
    values = [
        {**candidate(1), "input_value": "01"},
        {**candidate(1), "input_value": "1"},
        {**candidate(1), "input_value": "01"},
    ]
    result = resolve_attribute("name", values, policy())
    assert result == resolve_attribute("name", values[::-1], policy())
    assert result["state"] == "RESOLVED" and result["final_value"] == 1
    assert {c["input_value"]: c["occurrences"] for c in result["candidates"]} == {
        "01": 2,
        "1": 1,
    }


def mapping_config(conflict: str = "PRIORITY") -> dict:
    return {
        "entity_maps": [
            {
                "entity_type": "Partner",
                "table": table,
                "schema": "main",
                "key_fields": ["id"],
                "match_keys": ["code"],
                "field_maps": [{"target_attr": "name", "source_field": "name"}],
                "fusion": policy(rank, conflict=conflict),
            }
            for rank, table in enumerate(["a", "b"], 1)
        ]
    }


@pytest.fixture()
def setup(tmp_path: Path) -> Iterator[tuple[Session, Engine, int, int]]:
    source_path = tmp_path / "source.sqlite"
    source = create_engine(f"sqlite:///{source_path}")
    with source.begin() as conn:
        for table in ["a", "b"]:
            conn.execute(
                text(
                    f"CREATE TABLE {table} "
                    "(id INTEGER, code TEXT, name TEXT, secret TEXT)"
                )
            )
        conn.execute(
            text(
                "INSERT INTO a VALUES (1,'C1','First','do-not-copy'), "
                "(2,'C2','Same','secret')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO b VALUES (10,'C1','Second','hidden'), "
                "(20,'C2','Same','hidden')"
            )
        )
        conn.execute(
            text("CREATE TABLE rel (id INTEGER PRIMARY KEY, src INTEGER, dst INTEGER)")
        )
        conn.execute(text("INSERT INTO rel VALUES (1,1,2)"))
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        onto = Ontology(
            name="Fusion",
            iri="https://example.org/fusion#",
            status="PUBLISHED",
            current_revision=1,
        )
        session.add(onto)
        session.flush()
        session.add(
            OntologyRevision(
                ontology_id=onto.id,
                revision=1,
                ref_domains=[],
                ref_types=[],
                rules=[],
                resource_versions={},
            )
        )
        ds = create_datasource(
            session,
            DatasourceCreate(
                name="Source", kind="sqlite", params={"database": str(source_path)}
            ),
        )
        capture_metadata(session, ds.id)
        session.commit()
        yield session, source, ds.id, onto.id
    engine.dispose()
    source.dispose()


def publish(session: Session, onto_id: int, name: str, config: dict) -> MappingRevision:
    mapping = create_mapping(session, MappingCreate(name=name, ontology_id=onto_id))
    save_draft(session, mapping.id, MappingRevisionCreate.model_validate(config), 0)
    return publish_mapping(session, mapping.id, 0)


def decisions(session: Session, run: ExtractionRun) -> dict:
    graph = session.scalar(select(GraphRevision).where(GraphRevision.run_id == run.id))
    assert graph is not None
    return {
        iri: trace_entity_fusion(session, iri, graph.id)
        for iri in run.cfg_snapshot["fusion_evidence"]["entities"]
    }


def test_runtime_reverse_order_and_frozen_evidence(setup: tuple) -> None:
    session, source, ds_id, onto_id = setup
    first = publish(session, onto_id, "One", mapping_config())
    run = start_run(session, first.id, ds_id)
    assert run.status == "SUCCESS"
    evidence = decisions(session, run)
    conflict = next(value for value in evidence.values() if value["conflicts"])
    assert EntityFusionOut.model_validate(conflict).attributes[0].final_value == "First"
    assert conflict["attributes"][0]["reason"] == "SOURCE_PRIORITY"
    assert len(conflict["attributes"][0]["candidates"]) == 2
    assert "do-not-copy" not in str(run.cfg_snapshot)
    assert "secret" not in str(run.cfg_snapshot)
    config = mapping_config()
    config["entity_maps"].reverse()
    second = publish(session, onto_id, "Two", config)
    with source.begin() as conn:
        conn.execute(text("CREATE TABLE temp AS SELECT * FROM a ORDER BY id DESC"))
        conn.execute(text("DELETE FROM a"))
        conn.execute(text("INSERT INTO a SELECT * FROM temp"))
    rerun = start_run(session, second.id, ds_id)
    assert run.cfg_snapshot["fusion_evidence"] == rerun.cfg_snapshot["fusion_evidence"]
    with source.begin() as conn:
        conn.execute(text("UPDATE a SET name='Changed'"))
    session.expire_all()
    assert decisions(session, run) == evidence


def test_quarantine_excludes_entity_and_relations_and_keeps_old_graph_on_failure(
    setup: tuple,
) -> None:
    session, source, ds_id, onto_id = setup
    previous = start_run(
        session, publish(session, onto_id, "Baseline", mapping_config()).id, ds_id
    )
    previous_graph = get_current_graph(session)
    assert previous.status == "SUCCESS"
    config = mapping_config("QUARANTINE")
    config["rel_maps"] = [
        {
            "relation_type": "knows",
            "mode": "JUNCTION",
            "table": "rel",
            "source": {"field": "src", "ref_table": "a", "ref_field": "id"},
            "target": {"field": "dst", "ref_table": "a", "ref_field": "id"},
        }
    ]
    revision = publish(session, onto_id, "Isolation", config)
    run = start_run(session, revision.id, ds_id, publish=False)
    graph = session.scalar(select(GraphRevision).where(GraphRevision.run_id == run.id))
    assert run.status == "PARTIAL"
    assert (
        len(
            list(
                session.scalars(
                    select(EntityIdentity).where(
                        EntityIdentity.graph_revision_id == graph.id
                    )
                )
            )
        )
        == 1
    )
    assert not list(
        session.scalars(
            select(GraphTriple).where(GraphTriple.graph_revision_id == graph.id)
        )
    )
    result = next(
        r
        for r in decisions(session, run).values()
        if r["entity_state"] == "QUARANTINED"
    )
    assert result["attributes"][0]["final_value_present"] is False
    assert (
        trace_entity_evidence(session, result["entity"]["iri"], graph.id)[
            "quarantined_count"
        ]
        == 2
    )
    with source.begin() as conn:
        conn.execute(text("UPDATE b SET name='Conflict'"))
    failed = start_run(session, revision.id, ds_id)
    assert failed.status == "FAILED"
    assert failed.counts["entity_count"] == 0
    assert get_current_graph(session).id == previous_graph.id


@pytest.mark.parametrize("mode", ["JUNCTION", "ASSOCIATIVE", "FK"])
@pytest.mark.parametrize("missing", [None, ""])
def test_invalid_business_keys_cannot_resurrect_as_relation_stubs(
    setup: tuple, mode: str, missing: str | None
) -> None:
    session, source, ds_id, onto_id = setup
    baseline = publish(session, onto_id, "Baseline", mapping_config())
    assert start_run(session, baseline.id, ds_id).status == "SUCCESS"
    previous_id = get_current_graph(session).id
    config = mapping_config()
    config["rel_maps"] = [
        {
            "relation_type": "knows",
            "mode": mode,
            "table": "rel",
            "fk_field": "src",
            "source": {"field": "src", "ref_table": "a", "ref_field": "id"},
            "target": {"field": "dst", "ref_table": "a", "ref_field": "id"},
        }
    ]
    revision = publish(session, onto_id, "InvalidIdentity", config)
    with source.begin() as conn:
        for table in ["a", "b"]:
            conn.execute(
                text(f"UPDATE {table} SET code=:missing"), {"missing": missing}
            )
    failed = start_run(session, revision.id, ds_id)
    assert failed.status == "FAILED"
    assert failed.counts["entity_count"] == failed.counts["triple_count"] == 0
    assert failed.counts["quarantine_count"] == 5
    graph = session.scalar(
        select(GraphRevision).where(GraphRevision.run_id == failed.id)
    )
    assert graph is not None
    assert not list(
        session.scalars(
            select(EntityIdentity).where(EntityIdentity.graph_revision_id == graph.id)
        )
    )
    assert not list(
        session.scalars(
            select(GraphTriple).where(GraphTriple.graph_revision_id == graph.id)
        )
    )
    assert get_current_graph(session).id == previous_id


@pytest.mark.parametrize("target_table", ["good", "a"])
def test_fk_rejection_is_bound_to_the_actual_target_table(
    setup: tuple, target_table: str
) -> None:
    session, source, ds_id, onto_id = setup
    with source.begin() as conn:
        conn.execute(text("CREATE TABLE good (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(text("INSERT INTO good VALUES (1, 'Valid target')"))
        conn.execute(
            text(
                "CREATE TABLE employee (id INTEGER PRIMARY KEY, name TEXT, "
                "target_id INTEGER "
                f"REFERENCES {target_table}(id))"
            )
        )
        conn.execute(text("INSERT INTO employee VALUES (99, 'Employee', 1)"))
        for table in ["a", "b"]:
            conn.execute(text(f"UPDATE {table} SET code=NULL"))
    capture_metadata(session, ds_id)
    config = mapping_config()
    for name in ["good", "employee"]:
        config["entity_maps"].append(
            {
                "entity_type": name.title(),
                "table": name,
                "key_fields": ["id"],
                "field_maps": [{"target_attr": "name", "source_field": "name"}],
            }
        )
    config["rel_maps"] = [
        {
            "relation_type": "works",
            "mode": "FK",
            "table": "employee",
            "fk_field": "target_id",
        }
    ]
    run = start_run(session, publish(session, onto_id, "QualifiedFk", config).id, ds_id)
    graph = session.scalar(select(GraphRevision).where(GraphRevision.run_id == run.id))
    assert graph is not None and run.counts["entity_count"] == 2
    facts = list(
        session.scalars(
            select(GraphTriple).where(GraphTriple.graph_revision_id == graph.id)
        )
    )
    assert len(facts) == (1 if target_table == "good" else 0)
    if facts:
        assert facts[0].subject.endswith("Employee/99")
        assert facts[0].object_.endswith("Good/1")


def test_legacy_is_readable_but_cannot_run_without_explicit_policy(
    setup: tuple,
) -> None:
    session, _, ds_id, onto_id = setup
    revision = publish(session, onto_id, "LegacyFixture", mapping_config())
    run = start_run(session, revision.id, ds_id)
    graph = get_current_graph(session)
    iri = next(iter(run.cfg_snapshot["fusion_evidence"]["entities"]))
    run.cfg_snapshot = {
        key: value
        for key, value in run.cfg_snapshot.items()
        if key != "fusion_evidence"
    }
    revision.entity_maps = [
        {key: value for key, value in em.items() if key != "fusion"}
        for em in revision.entity_maps
    ]
    session.flush()
    result = trace_entity_fusion(session, iri, graph.id)
    assert result["evidence_state"] == "LEGACY"
    assert result["attributes"] == [] and result["conflicts"] == []
    with pytest.raises(KGError) as error:
        start_run(session, revision.id, ds_id)
    assert error.value.params["reason"] == "fusion_policy_required"
    preview = compile_mapping(session, revision.mapping_id, ds_id)
    assert preview["summary"]["error_count"] >= 1
    assert preview["entities"][0]["fusion_state"] == "LEGACY"


@pytest.mark.parametrize(
    "change,reason",
    [
        ("missing", "fusion_policy_required"),
        ("duplicate", "fusion_duplicate_source_mapping"),
        ("null", "fusion_inconsistent_policy"),
        ("row_key", "fusion_stable_row_key_required"),
    ],
)
def test_new_mapping_policy_validation(change: str, reason: str) -> None:
    maps = deepcopy(mapping_config()["entity_maps"])
    if change == "missing":
        maps[0].pop("fusion")
    if change == "duplicate":
        maps[1]["table"] = "a"
    if change == "null":
        maps[1]["fusion"]["null_policy"] = "KEEP"
    if change == "row_key":
        maps[1]["key_fields"] = []
    with pytest.raises(KGError) as error:
        validate_fusion_policies(maps)
    assert error.value.params["reason"] == reason


def test_business_key_incremental_remains_unsupported(setup: tuple) -> None:
    session, _, ds_id, onto_id = setup
    revision = publish(session, onto_id, "Append", mapping_config())
    with pytest.raises(KGError) as error:
        start_run(session, revision.id, ds_id, incremental=True)
    assert "incremental" in error.value.params["reason"]


def test_ai_append_preserves_existing_fusion_transforms_and_endpoint_fields(
    setup: tuple,
) -> None:
    session, _, _, onto_id = setup
    config = mapping_config()
    config["entity_maps"][0]["field_maps"][0].update(
        transform="TEMPLATE",
        transform_params={"template": "P-{value}"},
        null_policy="DEFAULT",
        default_value="unknown",
    )
    config["rel_maps"] = [
        {
            "relation_type": "knows",
            "mode": "JUNCTION",
            "table": "rel",
            "source": {
                "candidates": [
                    {
                        "field": "src",
                        "ref_table": "a",
                        "ref_field": "code",
                        "ref_entity_type": "Partner",
                    }
                ]
            },
            "target": {"field": "dst", "ref_table": "b", "ref_field": "id"},
        }
    ]
    mapping = create_mapping(
        session, MappingCreate(name="AiAppend", ontology_id=onto_id)
    )
    draft = save_draft(
        session, mapping.id, MappingRevisionCreate.model_validate(config), 0
    )
    previous_entities, previous_relations = (
        deepcopy(draft.entity_maps),
        deepcopy(draft.rel_maps),
    )
    suggestion = AiSuggestion(
        kind="MAPPING_SUGGEST",
        target_id=mapping.id,
        title="Synthetic append",
        payload={
            "entity_type": "Other",
            "table": "other",
            "key_fields": ["id"],
            "field_maps": [{"target_attr": "name", "source_field": "name"}],
        },
    )
    session.add(suggestion)
    session.flush()
    apply_suggestion(session, suggestion.id)
    updated = get_draft_revision(session, mapping.id)
    assert updated is not None and len(updated.entity_maps) == 3
    assert updated.entity_maps[:2] == previous_entities
    assert updated.rel_maps == previous_relations
