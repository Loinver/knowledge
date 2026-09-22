"""M-01 规则库：API、原子版本、真实语义结果、安全边界与迁移。"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest
from app.api.v1.governance import router
from app.core.db import Base, get_session
from app.core.error_codes import ErrorCode
from app.core.errors import KGError, install_error_handler
from app.domain import rule_service
from app.models.governance import Rule
from app.schemas.governance import RuleCreate
from app.semantics import rule_examples
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
URL = "/api/v1/governance/rules"
PREFIXES = """@prefix ex: <https://example.org/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""
SHAPE = (
    PREFIXES
    + """ex:RequiredName a sh:NodeShape ;
    sh:targetClass ex:Person ;
    sh:property [ sh:path ex:name ; sh:minCount 1 ; sh:datatype xsd:string ] .
"""
)
POSITIVE = PREFIXES + 'ex:Alice a ex:Person ; ex:name "Alice" .'
NEGATIVE = PREFIXES + "ex:Bob a ex:Person ."


def rule_payload(**overrides: Any) -> dict[str, Any]:
    return {
        "identifier": "PersonName",
        "name_i18n": {"zh-CN": "姓名必填", "en-US": "Required name"},
        "category": "completeness",
        "source_kind": "ENTERPRISE",
        "source_reference": "EXAMPLE-POLICY-01",
        "target_iri": "https://example.org/Person",
        "severity": "VIOLATION",
        "language": "SHACL",
        "expression": SHAPE,
        "execution": "AUTO",
        "positive_example": POSITIVE,
        "negative_example": NEGATIVE,
        **overrides,
    }


@pytest.fixture()
def sessions(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/rules.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def client(sessions: sessionmaker[Session]) -> Iterator[TestClient]:
    # Avoid application startup, which creates tables in the user's configured DB.
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    install_error_handler(app)
    app.dependency_overrides[get_session] = lambda: sessions()
    with TestClient(app) as client:
        yield client


def create(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post(URL, json=rule_payload(**overrides))
    assert response.status_code == 201, response.text
    assert response.headers["etag"] == '"1"'
    return response.json()


def test_crud_paging_source_filter_and_bilingual_search(client: TestClient) -> None:
    first = create(client)
    second = create(client, identifier="AStandard", source_kind="STANDARD")
    response = client.get(URL, params={"page_size": 1})
    assert response.status_code == 200
    assert response.json() == {"items": [second], "page": 1, "page_size": 1, "total": 2}
    assert client.get(URL, params={"page": 2, "page_size": 1}).json()["items"] == [
        first
    ]
    assert client.get(URL, params={"source_kind": "STANDARD"}).json()["items"] == [
        second
    ]
    for query in ("姓名", "required name", "PersonName", "EXAMPLE-POLICY"):
        assert client.get(URL, params={"q": query}).json()["total"] >= 1
    assert client.get(URL, params={"q": "%"}).json()["total"] == 0
    assert client.get(URL, params={"sort": "-id"}).json()["items"][0] == second
    fetched = client.get(f"{URL}/{first['id']}")
    assert fetched.json() == first
    assert fetched.headers["etag"] == '"1"'
    updated = client.put(
        f"{URL}/{first['id']}",
        headers={"If-Match": '"1"'},
        json=rule_payload(name_i18n={"zh-CN": "更新姓名"}),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == 2
    assert updated.json()["name_i18n"] == {"zh-CN": "更新姓名"}
    assert updated.headers["etag"] == '"2"'
    deleted = client.delete(f"{URL}/{first['id']}", headers={"If-Match": "2"})
    assert deleted.status_code == 204
    assert client.get(f"{URL}/{first['id']}").status_code == 404


def test_duplicate_identifier_and_revision_conflicts(client: TestClient) -> None:
    rule = create(client)
    path = f"{URL}/{rule['id']}"
    duplicate = client.post(URL, json=rule_payload())
    assert duplicate.status_code == 409
    assert duplicate.json()["params"]["reason"] == "rule_identifier_taken"
    for method, suffix in (("put", ""), ("delete", ""), ("post", "/test")):
        kwargs = {"json": rule_payload()} if method == "put" else {}
        for header in (None, "*", 'W/"1"', "0", "garbage"):
            headers = {} if header is None else {"If-Match": header}
            response = client.request(method, path + suffix, headers=headers, **kwargs)
            assert response.status_code == 400, response.text
            assert response.json()["code"] == "KG.INVALID_REQUEST"
        response = client.request(
            method, path + suffix, headers={"If-Match": "9"}, **kwargs
        )
        assert response.status_code == 409
        assert response.json()["code"] == "KG.REVISION_CONFLICT"
        assert response.json()["params"] == {
            "rule_id": rule["id"],
            "expected": 9,
            "actual": 1,
        }
    assert client.get(path).json() == rule


def test_actual_positive_negative_reports(client: TestClient) -> None:
    rule = create(client)
    response = client.post(f"{URL}/{rule['id']}/test", headers={"If-Match": '"1"'})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["rule_id"] == rule["id"]
    assert report["revision"] == 1
    assert report["state"] == "PASS"
    assert report["positive"]["conforms"] is True
    assert report["positive"]["state"] == "PASS"
    assert report["negative"]["conforms"] is False
    assert report["negative"]["state"] == "VIOLATION"
    assert "MinCountConstraintComponent" in report["negative"]["report_text"]
    assert "ex:Bob" in report["negative"]["report_text"]


@pytest.mark.parametrize("severity", ["INFO", "WARNING"])
@pytest.mark.parametrize("nested", [False, True])
def test_rule_severity_governs_real_reports_without_allowing_violations(
    client: TestClient, severity: str, nested: bool
) -> None:
    expression = SHAPE
    negative = NEGATIVE
    if nested:
        expression = SHAPE.replace(
            "sh:datatype xsd:string", "sh:node [ sh:minLength 2 ]"
        )
        negative = PREFIXES + 'ex:Bob a ex:Person ; ex:name "B" .'
    rule = create(
        client, severity=severity, expression=expression, negative_example=negative
    )
    response = client.post(f"{URL}/{rule['id']}/test", headers={"If-Match": "1"})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["state"] == "PASS"
    assert report["positive"]["conforms"] is True
    assert report["negative"]["conforms"] is False
    assert report["negative"]["state"] == "VIOLATION"
    assert f"Severity: sh:{severity.title()}" in report["negative"]["report_text"]
    assert "Severity: sh:Violation" not in report["negative"]["report_text"]


def test_expression_severity_must_match_rule_metadata(client: TestClient) -> None:
    expression = SHAPE + "ex:RequiredName sh:severity sh:Warning ."
    response = client.post(URL, json=rule_payload(expression=expression))
    assert response.status_code == 400
    assert response.json()["params"] == {
        "field": "expression",
        "reason": "severity_conflict",
    }
    rule = create(client, expression=expression, severity="WARNING")
    response = client.put(
        f"{URL}/{rule['id']}",
        headers={"If-Match": "1"},
        json=rule_payload(expression=expression, severity="INFO"),
    )
    assert response.status_code == 400
    assert response.json()["params"]["reason"] == "severity_conflict"
    assert client.get(f"{URL}/{rule['id']}").json() == rule


@pytest.mark.parametrize(
    ("positive", "negative"), [(POSITIVE, POSITIVE), (NEGATIVE, NEGATIVE)]
)
def test_unexpected_examples_are_not_pass(
    client: TestClient, positive: str, negative: str
) -> None:
    rule = create(client, positive_example=positive, negative_example=negative)
    response = client.post(f"{URL}/{rule['id']}/test", headers={"If-Match": "1"})
    assert response.status_code == 200
    assert response.json()["state"] == "VIOLATION"


@pytest.mark.parametrize("overrides", [{"language": "OWL"}, {"execution": "MANUAL"}])
def test_unsupported_rules_are_not_run(
    client: TestClient, overrides: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    rule = create(client, **overrides)

    def forbid_execution(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Unsupported or manual rule must not execute")

    monkeypatch.setattr(rule_service, "run_examples", forbid_execution)
    response = client.post(f"{URL}/{rule['id']}/test", headers={"If-Match": "1"})
    assert response.json() == {
        "rule_id": rule["id"],
        "revision": 1,
        "state": "NOT_RUN",
        "positive": None,
        "negative": None,
    }


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("expression", "not Turtle", "KG.INVALID_REQUEST"),
        ("positive_example", "not Turtle", "KG.INVALID_REQUEST"),
        ("negative_example", "not Turtle", "KG.INVALID_REQUEST"),
        (
            "expression",
            SHAPE.replace("sh:minCount 1", 'sh:minCount "one"'),
            "KG.INVALID_REQUEST",
        ),
        (
            "expression",
            SHAPE.replace("sh:targetClass ex:Person", "sh:targetClass ex:Other"),
            "KG.INVALID_REQUEST",
        ),
        (
            "positive_example",
            PREFIXES + "ex:Alice a ex:Other .",
            "KG.VALIDATION_VIOLATION",
        ),
        (
            "negative_example",
            PREFIXES + "ex:Bob a ex:Other .",
            "KG.VALIDATION_VIOLATION",
        ),
        ("name_i18n", {"en-US": "Name"}, "KG.INVALID_NAME"),
        ("name_i18n", {"zh-CN": " "}, "KG.INVALID_NAME"),
        ("name_i18n", {"zh-CN": "姓名", "en-US": " "}, "KG.INVALID_NAME"),
        ("target_iri", "relative/path", "KG.INVALID_IRI"),
        ("target_iri", "https://", "KG.INVALID_IRI"),
    ],
)
def test_invalid_payloads_return_structured_errors(
    client: TestClient, field: str, value: Any, code: str
) -> None:
    response = client.post(URL, json=rule_payload(**{field: value}))
    assert response.status_code in (400, 422), response.text
    assert response.json()["code"] == code
    assert response.json()["params"]["field"] == field
    assert client.get(URL).json()["total"] == 0


@pytest.mark.parametrize(
    "extra",
    [
        "ex:RequiredName sh:js [ sh:jsFunctionName 'evil' ] .",
        "ex:RequiredName sh:sparql [ sh:select 'SELECT * WHERE {?s ?p ?o}' ] .",
        "ex:RequiredName <http://www.w3.org/2002/07/owl#imports> "
        "<https://example.org/remote> .",
        "ex:RequiredName sh:rule [ a sh:SPARQLRule ; "
        "sh:construct 'SERVICE <https://example.org/> {}' ] .",
        "ex:RequiredName sh:deactivated true .",
        "ex:Other a sh:NodeShape ; sh:targetClass ex:OtherClass .",
        "ex:RequiredName <http://www.w3.org/ns/shacl#\\u0073parql> [] .",
        "ex:Custom a sh:ConstraintComponent ; sh:validator [] .",
    ],
)
def test_unsafe_or_ambiguous_shapes_are_rejected(
    client: TestClient, extra: str
) -> None:
    response = client.post(URL, json=rule_payload(expression=SHAPE + extra))
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "KG.INVALID_REQUEST"
    assert response.json()["params"]["field"] == "expression"


def test_update_validates_without_changing_saved_revision(client: TestClient) -> None:
    rule = create(client)
    path = f"{URL}/{rule['id']}"
    for patch in ({"name_i18n": {"en-US": "Only English"}}, {"expression": "bad"}):
        response = client.put(
            path, headers={"If-Match": "1"}, json=rule_payload(**patch)
        )
        assert response.status_code == 400
        assert client.get(path).json() == rule


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("identifier", " "),
        ("category", ""),
        ("source_reference", ""),
        ("source_kind", "unknown"),
        ("severity", "unknown"),
        ("language", "unknown"),
        ("execution", "unknown"),
        ("expression", ""),
        ("positive_example", ""),
        ("negative_example", ""),
    ],
)
def test_invalid_metadata_has_kg_error_contract(
    client: TestClient, field: str, value: str
) -> None:
    response = client.post(URL, json=rule_payload(**{field: value}))
    assert response.status_code == 400
    assert response.json()["code"] == "KG.INVALID_REQUEST"
    assert response.json()["params"]["issues"][0]["field"] == field


def test_atomic_update_allows_only_one_competing_writer(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    with sessions.begin() as session:
        rule_id = rule_service.create_rule(session, RuleCreate(**rule_payload())).id
    barrier = Barrier(2)

    def rendezvous(payload: RuleCreate) -> None:
        barrier.wait(timeout=5)

    monkeypatch.setattr(rule_service, "inspect_examples", rendezvous)

    def edit(name: str) -> str:
        try:
            with sessions.begin() as session:
                result = rule_service.update_rule(
                    session, rule_id, RuleCreate(**rule_payload(category=name)), 1
                )
                assert result.revision == 2
            return "updated"
        except KGError as exc:
            assert exc.code == ErrorCode.REVISION_CONFLICT
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(edit, ["one", "two"]))
    assert sorted(outcomes) == ["conflict", "updated"]
    with sessions() as session:
        assert rule_service.get_rule(session, rule_id).revision == 2


def test_create_rule_is_undone_by_outer_rollback(
    sessions: sessionmaker[Session],
) -> None:
    payload = RuleCreate(**rule_payload(language="OWL", execution="MANUAL"))
    with sessions.begin() as session:
        rule_service.create_rule(session, payload)
    with pytest.raises(RuntimeError, match="abort outer transaction"):
        with sessions.begin() as session:
            rule_service.create_rule(
                session, payload.model_copy(update={"identifier": "RolledBack"})
            )
            raise RuntimeError("abort outer transaction")
    with sessions() as session:
        assert list(session.scalars(select(Rule.identifier))) == [payload.identifier]


def test_update_rule_is_undone_by_outer_rollback(
    sessions: sessionmaker[Session],
) -> None:
    payload = RuleCreate(**rule_payload(language="OWL", execution="MANUAL"))
    with sessions.begin() as session:
        rule_id = rule_service.create_rule(session, payload).id
    with pytest.raises(RuntimeError, match="abort outer transaction"):
        with sessions.begin() as session:
            updated = rule_service.update_rule(
                session,
                rule_id,
                payload.model_copy(update={"category": "rolled_back"}),
                1,
            )
            assert updated.revision == 2
            raise RuntimeError("abort outer transaction")
    with sessions() as session:
        saved = rule_service.get_rule(session, rule_id)
        assert saved.revision == 1
        assert RuleCreate.model_validate(saved, from_attributes=True) == payload


def test_test_result_rechecks_saved_revision(
    sessions: sessionmaker[Session], client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    rule = create(client)
    real_run = rule_service.run_examples

    def concurrent_edit(payload: RuleCreate) -> tuple[dict[str, Any], dict[str, Any]]:
        result = real_run(payload)
        with sessions.begin() as session:
            saved = session.get(Rule, rule["id"])
            assert saved is not None
            saved.revision += 1
        return result

    monkeypatch.setattr(rule_service, "run_examples", concurrent_edit)
    response = client.post(f"{URL}/{rule['id']}/test", headers={"If-Match": "1"})
    assert response.status_code == 409, response.text
    assert response.json()["params"]["actual"] == 2


def test_runner_timeout_returns_error_and_releases_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(*args: Any, **kwargs: Any) -> None:
        assert kwargs["timeout"] == rule_examples.TIMEOUT_SECONDS
        raise subprocess.TimeoutExpired("rule-worker", kwargs["timeout"])

    monkeypatch.setattr(rule_examples.subprocess, "run", timeout)
    for _ in range(3):
        with pytest.raises(KGError) as error:
            rule_examples.inspect_examples(RuleCreate(**rule_payload()))
        assert error.value.code == ErrorCode.REASONER_UNAVAILABLE
        assert error.value.params["reason"] == "rule_runner_timeout"


def test_migration_upgrade_downgrade_replays_without_user_database(
    tmp_path: Path,
) -> None:
    database_url = f"sqlite:///{tmp_path}/migration.db"
    environment = {**os.environ, "KG_DATABASE_URL": database_url}

    def migrate(*args: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    migrate("upgrade", "head")
    engine = create_engine(database_url)
    assert "governance_rule" in inspect(engine).get_table_names()
    with Session(engine) as session:
        rule = rule_service.create_rule(session, RuleCreate(**rule_payload()))
        session.commit()
        assert session.scalar(select(Rule.identifier)) == rule.identifier
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO namespace (prefix, iri, protected) VALUES (:p, :i, 0)"),
            {"p": "example", "i": "https://example.org/"},
        )
    migrate("downgrade", "67ccedb5a0e9")
    assert "governance_rule" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT prefix FROM namespace")) == "example"
    migrate("upgrade", "head")
    assert "governance_rule" in inspect(engine).get_table_names()
    engine.dispose()
