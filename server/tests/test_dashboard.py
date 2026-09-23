"""工作台统计不能被列表分页截断，也不能把失败展示为空统计。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from app.api.errors import install_error_handler
from app.api.v1.dashboard import router
from app.core.db import Base, get_session
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain import dashboard_service
from app.domain.account_service import issue_session
from app.domain.extraction_service import switch_current
from app.models.account import User
from app.models.data_access import Datasource, Mapping, MappingRevision
from app.models.domain import (
    BusinessDomain,
    DomainMember,
    DomainRevision,
    Ontology,
    OntologyResourceRef,
    OntologyRevision,
)
from app.models.enums import ResourceKind, ResourceStatus, RunResult, UserStatus
from app.models.extraction import ExtractionRun, GraphRevision, Quarantine
from app.models.resource import ModelResource, Namespace, ResourceRevision
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

URL = "/api/v1/dashboard/stats"
EMPTY_STATS = {
    "entity_types": 0,
    "relation_types": 0,
    "domains": 0,
    "ontologies": 0,
    "datasources": 0,
    "mappings": 0,
    "runs": 0,
    "current_graph_id": None,
    "result_set_count": 0,
    "quarantine_count": 0,
    "unpublished_count": 0,
}


@pytest.fixture()
def sessions(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/dashboard.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def client(sessions: sessionmaker[Session]) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    install_error_handler(app)

    def isolated_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = isolated_session
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def headers(sessions: sessionmaker[Session]) -> dict[str, str]:
    with sessions() as session:
        user = User(
            username="dashboard-viewer",
            email="dashboard@example.org",
            password_hash="unused-in-access-token-tests",
        )
        session.add(user)
        session.flush()
        tokens = issue_session(session, user)
        session.commit()
        return {"Authorization": f"Bearer {tokens.access_token}"}


def test_empty_stats_have_a_complete_success_envelope(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.get(URL, headers=headers)
    assert response.status_code == 200
    assert json.loads(response.text) == {
        "code": "KG.OK",
        "message": "OK",
        "data": EMPTY_STATS,
    }


def test_totals_cover_all_pages_and_follow_the_current_result_set(
    sessions: sessionmaker[Session], client: TestClient, headers: dict[str, str]
) -> None:
    with sessions() as session:
        namespace = Namespace(prefix="dashboard", iri="https://example.org/dashboard/")
        session.add(namespace)
        session.flush()

        resources = []
        for kind, count, drafts in (
            (ResourceKind.ENTITY, 57, 17),
            (ResourceKind.OBJECT_PROP, 58, 19),
            (ResourceKind.DATATYPE_PROP, 3, 3),
            (ResourceKind.ASSOC, 4, 4),
            (ResourceKind.DOMAIN, 2, 2),
            (ResourceKind.ONTOLOGY, 2, 2),
        ):
            for index in range(count):
                resources.append(
                    ModelResource(
                        kind=kind,
                        name=f"{kind.value}{index}",
                        iri=f"{namespace.iri}{kind.value}{index}",
                        namespace_id=namespace.id,
                        status=ResourceStatus.DRAFT
                        if index < drafts
                        else ResourceStatus.PUBLISHED,
                    )
                )
        resources[56].status = ResourceStatus.ARCHIVED
        domains = [
            BusinessDomain(
                name=f"Domain{index}",
                iri=f"{namespace.iri}Domain{index}",
                status=ResourceStatus.DRAFT if index < 21 else ResourceStatus.PUBLISHED,
            )
            for index in range(59)
        ]
        ontologies = [
            Ontology(
                name=f"Ontology{index}",
                iri=f"{namespace.iri}Ontology{index}",
                status=ResourceStatus.DRAFT if index < 23 else ResourceStatus.PUBLISHED,
            )
            for index in range(60)
        ]
        session.add_all(resources + domains + ontologies)
        session.add_all(Datasource(name=f"Source{i}", kind="sqlite") for i in range(61))
        session.flush()
        mappings = [
            Mapping(name=f"Mapping{index}", ontology_id=ontologies[-1].id)
            for index in range(205)
        ]
        session.add_all(mappings)
        session.flush()
        revisions = [
            MappingRevision(
                mapping_id=mappings[0].id, revision=revision, onto_version=1
            )
            for revision in (1, 2)
        ]
        session.add_all(revisions)
        for revision in (1, 2):
            session.add(
                ResourceRevision(
                    resource_id=resources[55].id,
                    revision=revision,
                    payload={},
                    checksum="test",
                )
            )
            session.add(
                DomainRevision(domain_id=domains[-1].id, revision=revision, payload={})
            )
            session.add(
                OntologyRevision(ontology_id=ontologies[-1].id, revision=revision)
            )
        for index in (0, 1):
            session.add(
                DomainMember(domain_id=domains[index].id, resource_id=resources[55].id)
            )
            session.add(
                OntologyResourceRef(
                    ontology_id=ontologies[index].id, resource_id=resources[55].id
                )
            )
        session.flush()
        runs = [
            ExtractionRun(mapping_revision_id=revisions[0].id, status=RunResult.SUCCESS)
            for _ in range(64)
        ]
        runs[17].status = RunResult.PARTIAL
        runs[-3].status = RunResult.FAILED
        runs[-2].status = RunResult.CANCELLED
        runs[-1].status = RunResult.FAILED
        session.add_all(runs)
        session.flush()
        graphs = [
            GraphRevision(run_id=run.id, is_current=index == 17, publishable=True)
            for index, run in enumerate(runs[:61])
        ]
        session.add_all(graphs)
        for run, count in (
            (runs[17], 201),
            (runs[0], 203),
            (runs[60], 5),
            (runs[-1], 7),
        ):
            session.add_all(
                Quarantine(
                    run_id=run.id,
                    table_name="sample",
                    row_key=str(index),
                    field="value",
                    rule_id="sample-rule",
                )
                for index in range(count)
            )
        session.commit()
        current_id, historical_id = graphs[17].id, graphs[0].id

    response = client.get(URL, headers=headers)
    assert response.status_code == 200
    stats = response.json()
    assert stats == {
        "entity_types": 57,
        "relation_types": 58,
        "domains": 59,
        "ontologies": 60,
        "datasources": 61,
        "mappings": 205,
        "runs": 64,
        "current_graph_id": current_id,
        "result_set_count": 61,
        "quarantine_count": 201,
        "unpublished_count": 80,
    }

    with sessions() as session:
        switch_current(session, historical_id)
        session.commit()
    assert client.get(URL, headers=headers).json() == {
        **stats,
        "current_graph_id": historical_id,
        "quarantine_count": 203,
    }

    with sessions() as session:
        current = session.get(GraphRevision, historical_id)
        assert current is not None
        current.is_current = False
        session.commit()
    assert client.get(URL, headers=headers).json() == {
        **stats,
        "current_graph_id": None,
        "quarantine_count": 0,
    }


@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_stats_require_a_valid_access_token(
    client: TestClient, token: str | None
) -> None:
    response = client.get(
        URL, headers={"Authorization": f"Bearer {token}"} if token else {}
    )
    assert response.status_code == 401
    body = json.loads(response.text)
    assert body["code"] == "AUTH.TOKEN_EXPIRED"
    assert body["data"] is None
    assert set(body) == {"code", "message", "params", "data"}


def test_disabled_users_cannot_read_stats(
    sessions: sessionmaker[Session], client: TestClient, headers: dict[str, str]
) -> None:
    with sessions() as session:
        user = session.scalars(select(User)).one()
        user.status = UserStatus.DISABLED
        session.commit()
    response = client.get(URL, headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "AUTH.USER_DISABLED"
    assert response.json()["data"] is None


def test_service_errors_are_not_returned_as_empty_stats(
    client: TestClient, headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(_session: Session) -> dict[str, int | None]:
        raise KGError(ErrorCode.SOURCE_UNREACHABLE, {"reason": "stats_unavailable"})

    monkeypatch.setattr(dashboard_service, "get_stats", fail)
    response = client.get(URL, headers=headers)
    assert response.status_code == 503
    assert json.loads(response.text) == {
        "code": "KG.SOURCE_UNREACHABLE",
        "message": "KG.SOURCE_UNREACHABLE",
        "params": {"reason": "stats_unavailable"},
        "data": None,
    }


def test_database_errors_propagate(sessions: sessionmaker[Session]) -> None:
    with sessions() as session:
        # A missing table is a real query failure, never an empty catalog.
        session.connection().exec_driver_sql("DROP TABLE quarantine")
        with pytest.raises(OperationalError):
            dashboard_service.get_stats(session)
