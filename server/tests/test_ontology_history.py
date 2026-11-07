"""PC13：逐资源/规则冻结阅读、成员隔离与读操作零写入。"""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from app.api.errors import install_error_handler
from app.api.v1.ontology_history import router
from app.core.db import Base, get_session
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.iri_service import register_namespace
from app.domain.ontology_history_service import (
    get_revision_contents,
    get_revision_resource,
    get_revision_rule,
)
from app.domain.ontology_service import create_ontology, publish_ontology
from app.domain.relation_service import create_relation_type
from app.domain.resource_lifecycle import unpublish_resource
from app.domain.status_service import publish_resource
from app.domain.type_service import create_entity_type, update_entity_type
from app.models.domain import (
    Ontology,
    OntologyResourceRef,
    OntologyRevision,
    OntologyRuleRef,
)
from app.models.governance import Rule
from app.models.resource import ModelResource, ResourceRevision
from app.schemas.governance import RuleOut
from app.schemas.ontology import OntologyCreate
from app.schemas.ontology_history import HistorySnapshotState
from app.schemas.relation import (
    CardinalitySpec,
    EndpointSpec,
    OwlFeatures,
    RelationTypeCreate,
)
from app.schemas.type import DataTypePropCreate, EntityTypeCreate, EntityTypeUpdate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, event, select, update
from sqlalchemy.orm import Session


@pytest.fixture()
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/history.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


def _publish(
    session: Session, name: str = "Employee"
) -> tuple[Ontology, ModelResource, Rule]:
    namespace = register_namespace(
        session, name.lower(), f"https://example.org/{name}#"
    )
    resource = create_entity_type(
        session,
        EntityTypeCreate(
            name=name,
            namespace_id=namespace.id,
            label_i18n={"zh-CN": "员工", "en-US": name},
            definition_i18n={"zh-CN": "冻结定义", "en-US": "Frozen definition"},
            data_props=[
                DataTypePropCreate(
                    name="code",
                    label_i18n={"zh-CN": "编号", "en-US": "Code"},
                    datatype="string",
                    nullable=False,
                    default_value="original",
                    min_cardinality=1,
                    max_cardinality=1,
                    min_value="a",
                    max_value="z",
                    source_clause_ref="example#1",
                )
            ],
        ),
    )
    publish_resource(session, resource)
    rule = Rule(
        identifier=f"RULE-{name}",
        name_i18n={"zh-CN": "规则", "en-US": "Rule"},
        category="core",
        source_kind="ENTERPRISE",
        source_reference="example#1",
        target_iri=resource.iri,
        severity="WARNING",
        language="OWL",
        expression="original expression",
        execution="MANUAL",
        positive_example="positive",
        negative_example="negative",
        revision=1,
    )
    session.add(rule)
    session.flush()
    onto = create_ontology(
        session,
        OntologyCreate(
            name=f"{name}Ontology",
            iri=f"https://example.org/ontology/{name}",
            label_i18n={"zh-CN": "冻结本体"},
            ref_resource_ids=[resource.id],
            rule_ids=[rule.id],
        ),
    )
    publish_ontology(session, onto)
    session.commit()
    return onto, resource, rule


def _frozen(session: Session, ontology_id: int) -> OntologyRevision:
    return session.scalars(
        select(OntologyRevision).where(
            OntologyRevision.ontology_id == ontology_id,
            OntologyRevision.revision == 1,
        )
    ).one()


def _client(session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    install_error_handler(app)
    app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


def test_current_edits_and_republish_preserve_old_resource_and_rule(
    session: Session,
) -> None:
    onto, resource, rule = _publish(session)
    before_resource = get_revision_resource(session, onto.id, 1, resource.id)
    before_rule = get_revision_rule(session, onto.id, 1, rule.id)
    before_contents = get_revision_contents(session, onto.id, 1)
    frozen_rules = deepcopy(_frozen(session, onto.id).rules)
    assert before_rule.snapshot == RuleOut.model_validate(rule)
    assert frozen_rules[0]["snapshot"] == RuleOut.model_validate(rule).model_dump(
        mode="json"
    )
    prop = before_resource.snapshot.datatype_props[0]
    assert (
        prop.default_value,
        prop.label_i18n,
        prop.min_cardinality,
        prop.max_cardinality,
    ) == ("original", {"zh-CN": "编号", "en-US": "Code"}, 1, 1)
    assert (prop.min_value, prop.max_value, prop.source_clause_ref) == (
        "a",
        "z",
        "example#1",
    )

    unpublish_resource(session, resource)
    update_entity_type(
        session,
        resource,
        EntityTypeUpdate(
            if_match=1,
            edit_revision=resource.edit_revision,
            label_i18n={"zh-CN": "新标签"},
            data_props=[
                DataTypePropCreate(name="code", datatype="string", default_value="new")
            ],
        ),
    )
    publish_resource(session, resource)
    rule.name_i18n = {"zh-CN": "新规则"}
    rule.expression = "new expression"
    rule.source_reference = "example#2"
    rule.revision = 2
    session.execute(
        update(OntologyRuleRef)
        .where(OntologyRuleRef.ontology_id == onto.id)
        .values(pinned_revision=2)
    )
    publish_ontology(session, onto)
    session.commit()

    assert get_revision_resource(session, onto.id, 1, resource.id) == before_resource
    assert get_revision_rule(session, onto.id, 1, rule.id) == before_rule
    assert get_revision_contents(session, onto.id, 1) == before_contents
    assert _frozen(session, onto.id).rules == frozen_rules
    assert get_revision_resource(session, onto.id, 2, resource.id).revision == 2
    newer = get_revision_rule(session, onto.id, 2, rule.id)
    assert newer.revision == 2
    assert newer.snapshot is not None and newer.snapshot.expression == "new expression"


def test_explicit_resource_pin_uses_older_revision(session: Session) -> None:
    onto, resource, _rule = _publish(session)
    unpublish_resource(session, resource)
    resource.label_i18n = {"zh-CN": "第二版"}
    publish_resource(session, resource)
    session.execute(
        update(OntologyResourceRef)
        .where(OntologyResourceRef.ontology_id == onto.id)
        .values(pinned_revision=1)
    )
    publish_ontology(session, onto)
    session.commit()
    detail = get_revision_resource(session, onto.id, 2, resource.id)
    assert detail.revision == 1
    assert detail.snapshot.label_i18n == {"zh-CN": "员工", "en-US": "Employee"}


@pytest.mark.parametrize("missing", [True, False])
def test_legacy_rule_without_snapshot_is_unavailable(
    session: Session, missing: bool
) -> None:
    onto, _resource, rule = _publish(session)
    frozen = _frozen(session, onto.id)
    legacy = deepcopy(frozen.rules)
    if missing:
        legacy[0].pop("snapshot")
    else:
        legacy[0]["snapshot"] = None
    frozen.rules = legacy
    rule.expression = "must never be returned"
    rule.source_reference = "current-only"
    rule.revision = 2
    session.execute(
        delete(OntologyRuleRef).where(OntologyRuleRef.ontology_id == onto.id)
    )
    session.commit()
    detail = get_revision_rule(session, onto.id, 1, rule.id)
    assert detail.snapshot_state == HistorySnapshotState.UNAVAILABLE
    assert detail.snapshot is None
    assert (detail.revision, detail.source_reference) == (1, "example#1")
    assert (
        get_revision_contents(session, onto.id, 1).rules[0].snapshot_state
        == HistorySnapshotState.UNAVAILABLE
    )
    with _client(session) as client:
        response = client.get(
            f"/api/v1/ontologies/{onto.id}/revisions/1/rules/{rule.id}"
        )
    assert response.status_code == 200
    assert response.json()["snapshot_state"] == "UNAVAILABLE"
    assert response.json()["snapshot"] is None
    assert frozen.rules == legacy


def test_membership_comes_only_from_requested_frozen_revision(session: Session) -> None:
    onto, resource, rule = _publish(session)
    _other, foreign_resource, foreign_rule = _publish(session, "Department")
    session.execute(
        delete(OntologyResourceRef).where(OntologyResourceRef.ontology_id == onto.id)
    )
    session.execute(
        delete(OntologyRuleRef).where(OntologyRuleRef.ontology_id == onto.id)
    )
    session.add(
        OntologyResourceRef(ontology_id=onto.id, resource_id=foreign_resource.id)
    )
    session.add(
        OntologyRuleRef(ontology_id=onto.id, rule_id=foreign_rule.id, pinned_revision=1)
    )
    session.commit()
    with _client(session) as client:
        prefix = f"/api/v1/ontologies/{onto.id}/revisions/1"
        for path in (f"resources/{foreign_resource.id}", f"rules/{foreign_rule.id}"):
            response = client.get(f"{prefix}/{path}")
            assert response.status_code == 404
            assert response.json()["code"] == "KG.RESOURCE_NOT_FOUND"
        assert client.get(f"{prefix}/resources/{resource.id}").status_code == 200
        assert client.get(f"{prefix}/rules/{rule.id}").status_code == 200
        contents = client.get(f"{prefix}/contents").json()
        prop = session.scalar(
            select(ModelResource).where(ModelResource.name == "Employee.code")
        )
        assert prop is not None
        assert [item["resource_id"] for item in contents["resources"]] == [
            resource.id,
            prop.id,
        ]
        assert [item["rule_id"] for item in contents["rules"]] == [rule.id]


def test_stale_rule_pin_rejects_publish_and_preserves_history(session: Session) -> None:
    onto, _resource, rule = _publish(session)
    original = deepcopy(_frozen(session, onto.id).rules)
    original_edit = onto.edit_revision
    session.commit()
    # The publishing session still has revision 1 in its identity map.
    with Session(session.get_bind()) as writer:
        writer.execute(
            update(Rule)
            .where(Rule.id == rule.id)
            .values(revision=2, expression="other writer")
        )
        writer.commit()
    assert rule.revision == 1
    with pytest.raises(KGError) as caught:
        publish_ontology(session, onto)
    assert caught.value.code == ErrorCode.REVISION_CONFLICT
    assert caught.value.params == {"rule_id": rule.id, "expected": 1, "actual": 2}
    session.rollback()
    assert onto.current_revision == 1
    assert onto.edit_revision == original_edit
    assert _frozen(session, onto.id).rules == original
    assert len(session.scalars(select(OntologyRevision)).all()) == 1


def test_missing_pinned_resource_history_does_not_fall_back(session: Session) -> None:
    onto, resource, _rule = _publish(session)
    frozen = _frozen(session, onto.id)
    frozen.resource_versions = {str(resource.id): 99}
    session.commit()
    with _client(session) as client:
        response = client.get(
            f"/api/v1/ontologies/{onto.id}/revisions/1/resources/{resource.id}"
        )
    assert response.status_code == 404
    assert response.json()["code"] == "KG.REVISION_NOT_FOUND"
    assert response.json()["params"] == {"resource_id": resource.id, "revision": 99}


@pytest.mark.parametrize("pin", [True, "1", 0, -1])
def test_invalid_resource_pins_are_rejected(session: Session, pin: object) -> None:
    onto, resource, _rule = _publish(session)
    # Force the malformed JSON into storage: Python considers True equal to 1,
    # so assigning an ORM JSON attribute alone may not emit an UPDATE.
    session.execute(
        update(OntologyRevision)
        .where(OntologyRevision.ontology_id == onto.id)
        .values(resource_versions={str(resource.id): pin})
    )
    session.commit()
    session.expire_all()
    with pytest.raises(KGError) as caught:
        get_revision_contents(session, onto.id, 1)
    assert caught.value.code == ErrorCode.VALIDATION_VIOLATION
    assert caught.value.params["reason"] == "invalid_resource_versions"


def test_mismatched_rule_snapshot_does_not_masquerade_as_pinned_version(
    session: Session,
) -> None:
    onto, _resource, rule = _publish(session)
    frozen = _frozen(session, onto.id)
    damaged = deepcopy(frozen.rules)
    damaged[0]["snapshot"]["revision"] = 2
    frozen.rules = damaged
    session.commit()
    with pytest.raises(KGError) as caught:
        get_revision_rule(session, onto.id, 1, rule.id)
    assert caught.value.code == ErrorCode.VALIDATION_VIOLATION
    assert caught.value.params["reason"] == "invalid_rule_snapshot"


def test_reads_emit_only_selects_and_return_detached_content(session: Session) -> None:
    onto, resource, rule = _publish(session)
    original_rules = deepcopy(_frozen(session, onto.id).rules)
    frozen_resource = session.scalars(
        select(ResourceRevision).where(
            ResourceRevision.resource_id == resource.id,
            ResourceRevision.revision == 1,
        )
    ).one()
    original_payload = deepcopy(frozen_resource.payload)
    bind = session.get_bind()
    statements: list[str] = []

    def capture(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    rule.expression = "pending change must not autoflush"
    event.listen(bind, "before_cursor_execute", capture)
    try:
        detail = get_revision_resource(session, onto.id, 1, resource.id)
        rule_detail = get_revision_rule(session, onto.id, 1, rule.id)
        assert rule_detail.snapshot is not None
        detail.snapshot.datatype_props[0].default_value = "mutated DTO"
        assert detail.snapshot.label_i18n is not None
        detail.snapshot.label_i18n["zh-CN"] = "mutated DTO"
        rule_detail.snapshot.name_i18n["zh-CN"] = "mutated DTO"
        with _client(session) as client:
            prefix = f"/api/v1/ontologies/{onto.id}/revisions/1"
            for path in ("contents", f"resources/{resource.id}", f"rules/{rule.id}"):
                response = client.get(f"{prefix}/{path}")
                assert response.status_code == 200, response.text
                assert response.json()
        assert session.is_modified(rule)
        assert statements and all(
            sql.lstrip().upper().startswith("SELECT") for sql in statements
        )
        assert all(
            "governance_rule" not in sql and "model_resource" not in sql
            for sql in statements
        )
        assert not session.new and not session.deleted
        assert set(session.dirty) == {rule}
    finally:
        event.remove(bind, "before_cursor_execute", capture)
        session.rollback()
    assert _frozen(session, onto.id).rules == original_rules
    assert (
        session.scalars(
            select(ResourceRevision).where(
                ResourceRevision.resource_id == resource.id,
                ResourceRevision.revision == 1,
            )
        )
        .one()
        .payload
        == original_payload
    )
    assert rule.expression == "original expression"


def test_relation_snapshot_retains_cardinalities_roles_and_owl(
    session: Session,
) -> None:
    onto, resource, _rule = _publish(session)
    relation = create_relation_type(
        session,
        RelationTypeCreate(
            name="WorksWith",
            namespace_id=resource.namespace_id,
            label_i18n={"zh-CN": "合作"},
            domain_spec=EndpointSpec(
                type_id=resource.id,
                cardinality=CardinalitySpec(
                    min=1, max=-1, role_label_i18n={"zh-CN": "主端基数"}
                ),
                role_i18n={"zh-CN": "主端"},
            ),
            range_spec=EndpointSpec(type_id=resource.id),
            owl=OwlFeatures(symmetric=True),
        ),
    )
    publish_resource(session, relation)
    session.add(OntologyResourceRef(ontology_id=onto.id, resource_id=relation.id))
    publish_ontology(session, onto)
    session.commit()
    snapshot = get_revision_resource(session, onto.id, 2, relation.id).snapshot
    assert snapshot.object_prop is not None and snapshot.owl is not None
    assert snapshot.object_prop.domain_cardinality.min == 1
    assert snapshot.object_prop.domain_cardinality.role_label_i18n == {
        "zh-CN": "主端基数"
    }
    assert snapshot.object_prop.domain_role_i18n == {"zh-CN": "主端"}
    assert snapshot.owl.symmetric


def test_api_missing_revision_validation_and_openapi_types(session: Session) -> None:
    onto, resource, _rule = _publish(session)
    with _client(session) as client:
        missing = client.get(f"/api/v1/ontologies/{onto.id}/revisions/99/contents")
        assert missing.status_code == 404
        assert missing.json()["code"] == "KG.REVISION_NOT_FOUND"
        invalid = client.get(
            f"/api/v1/ontologies/{onto.id}/revisions/0/resources/{resource.id}"
        )
        assert invalid.status_code == 422
        schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert schemas["OntologyHistoryResourceOut"]["properties"]["snapshot"][
        "$ref"
    ].endswith("/HistoryResourceSnapshot")
    assert schemas["HistoryResourceSnapshot"]["properties"]["datatype_props"]["items"][
        "$ref"
    ].endswith("/HistoryPropertySnapshot")
    assert schemas["HistorySnapshotState"]["enum"] == ["AVAILABLE", "UNAVAILABLE"]
