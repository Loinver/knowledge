"""M-01 规则与本体装配的来源追溯。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.api.errors import install_error_handler
from app.api.v1.ontologies import router as ontology_router
from app.core.db import Base, get_session
from app.domain.ontology_service import create_ontology, publish_ontology
from app.models.domain import OntologyRevision, OntologyRuleRef
from app.models.governance import Rule
from app.schemas.ontology import OntologyCreate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


@pytest.fixture()
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/rule-trace.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


def _rule(session: Session) -> Rule:
    item = Rule(
        identifier="STD-ENTITY-001",
        name_i18n={"zh-CN": "实体命名", "en-US": "Entity naming"},
        category="core",
        source_kind="STANDARD",
        source_reference="GB/T 48000.3-2026#5.1",
        target_iri="https://example.org/kg#Person",
        severity="VIOLATION",
        language="SHACL",
        expression="@prefix sh: <http://www.w3.org/ns/shacl#> .",
        execution="AUTO",
        positive_example="@prefix ex: <https://example.org/> .",
        negative_example="@prefix ex: <https://example.org/> .",
        revision=1,
    )
    session.add(item)
    session.flush()
    return item


def test_rule_source_is_pinned_into_ontology_revision_and_queryable(
    session: Session,
) -> None:
    rule = _rule(session)
    onto = create_ontology(
        session,
        OntologyCreate(
            name="RuleTrace",
            iri="https://example.org/ontology/rule-trace",
            label_i18n={"zh-CN": "规则追溯"},
            rule_ids=[rule.id],
        ),
    )
    session.commit()
    assert session.scalar(select(OntologyRuleRef.rule_id)) == rule.id
    publish_ontology(session, onto)
    session.commit()
    revision = onto.current_revision
    snapshot = session.scalar(
        select(OntologyRevision).where(
            OntologyRevision.ontology_id == onto.id,
            OntologyRevision.revision == revision,
        )
    )
    assert snapshot is not None
    assert snapshot.rules == [
        {
            "rule_id": rule.id,
            "identifier": rule.identifier,
            "revision": 1,
            "source_kind": "STANDARD",
            "source_reference": "GB/T 48000.3-2026#5.1",
        }
    ]


def test_rule_trace_endpoint_returns_pinned_source(session: Session) -> None:
    rule = _rule(session)
    onto = create_ontology(
        session,
        OntologyCreate(
            name="RuleTraceApi",
            iri="https://example.org/ontology/rule-trace-api",
            label_i18n={"zh-CN": "规则追溯"},
            rule_ids=[rule.id],
        ),
    )
    session.commit()
    app = FastAPI()
    app.include_router(ontology_router, prefix="/api/v1")
    install_error_handler(app)
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        response = client.get(f"/api/v1/ontologies/{onto.id}/rules")
    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            "rule_id": rule.id,
            "identifier": "STD-ENTITY-001",
            "revision": 1,
            "source_kind": "STANDARD",
            "source_reference": "GB/T 48000.3-2026#5.1",
        }
    ]
