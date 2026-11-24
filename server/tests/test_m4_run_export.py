"""M-07 运行报告：独立 JSON 回读、历史不漂移、失败保护与凭据白名单。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.api.errors import install_error_handler
from app.api.v1.extraction import router
from app.core.db import Base, get_session
from app.domain.extraction_service import switch_current
from app.models.data_access import Mapping, MappingRevision
from app.models.domain import Ontology
from app.models.enums import RunResult
from app.models.extraction import ExtractionRun, GraphRevision
from app.schemas.extraction import ExtractionRunExport
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


@pytest.fixture()
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_engine(
        f"sqlite:///{tmp_path}/run-export.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        ontology = Ontology(name="Report", iri="https://example.org/report#")
        db.add(ontology)
        db.flush()
        mapping = Mapping(name="ReportMapping", ontology_id=ontology.id)
        db.add(mapping)
        db.flush()
        db.add(MappingRevision(mapping_id=mapping.id, revision=1, onto_version=3))
        db.commit()
        yield db
    engine.dispose()


@pytest.fixture()
def client(session: Session) -> Iterator[TestClient]:
    app = FastAPI()
    install_error_handler(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as test_client:
        yield test_client


def make_run(
    session: Session, status: RunResult = RunResult.SUCCESS
) -> tuple[ExtractionRun, GraphRevision]:
    revision = session.scalars(select(MappingRevision)).one()
    run = ExtractionRun(
        mapping_revision_id=revision.id,
        status=status,
        cfg_snapshot={
            "mapping_revision_id": revision.id,
            "datasource_id": 7,
            "onto_version": 3,
            "namespace": "https://example.org/kg/",
        },
        counts={
            "entity_count": 5,
            "triple_count": 8,
            "quarantine_count": 1 if status == RunResult.PARTIAL else 0,
            "evidence_count": 13,
            "derived_edge_count": 0,
        },
        fingerprint="f" * 64,
        started_at=datetime(2026, 9, 23, 1, tzinfo=UTC),
        finished_at=datetime(2026, 9, 23, 2, tzinfo=UTC),
    )
    session.add(run)
    session.flush()
    graph = GraphRevision(
        run_id=run.id,
        publishable=status in (RunResult.SUCCESS, RunResult.PARTIAL),
        is_current=False,
        published_at=run.finished_at,
    )
    session.add(graph)
    session.commit()
    return run, graph


@pytest.mark.parametrize("status", [RunResult.SUCCESS, RunResult.PARTIAL])
def test_download_roundtrip(
    client: TestClient, session: Session, status: RunResult
) -> None:
    run, graph = make_run(session, status)
    response = client.get(f"/api/v1/extraction/runs/{run.id}/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="run-{run.id}.json"'
    )
    assert response.headers["cache-control"] == "no-store"
    payload = json.loads(response.content)
    assert "code" not in payload  # 文件不是 API 响应外壳。
    report = ExtractionRunExport.model_validate(payload)
    assert report.schema_version == 1
    assert report.run_id == run.id
    assert report.mapping_revision_id == run.mapping_revision_id
    assert report.datasource_id == 7
    assert report.ontology_revision == 3
    assert report.status == status
    assert report.counts == run.counts
    assert report.fingerprint == run.fingerprint
    assert report.started_at == run.started_at
    assert report.finished_at == run.finished_at
    assert report.publication is not None
    assert report.publication.graph_revision_id == graph.id
    assert report.publication.published_at == graph.published_at


def test_historical_report_ignores_current_mapping_and_graph(
    client: TestClient, session: Session
) -> None:
    old_run, old_graph = make_run(session)
    new_run, new_graph = make_run(session)
    switch_current(session, old_graph.id)
    session.commit()
    url = f"/api/v1/extraction/runs/{old_run.id}/export"
    before = client.get(url).content

    mapping = session.scalars(select(Mapping)).one()
    mapping.current_revision = 2
    session.add(MappingRevision(mapping_id=mapping.id, revision=2, onto_version=99))
    switch_current(session, new_graph.id)
    session.commit()
    assert client.get(url).content == before
    assert new_graph.is_current is True
    assert old_graph.is_current is False
    assert json.loads(before)["publication"]["graph_revision_id"] != new_graph.id
    assert json.loads(before)["run_id"] != new_run.id
    assert not session.new and not session.dirty and not session.deleted


@pytest.mark.parametrize("status", [RunResult.FAILED, RunResult.CANCELLED])
def test_failed_and_cancelled_runs_never_export_a_publication(
    client: TestClient, session: Session, status: RunResult
) -> None:
    _, previous = make_run(session)
    switch_current(session, previous.id)
    run, graph = make_run(session, status)
    # 即使遗留图谱行状态不一致，也不能伪造失败运行已发布。
    graph.publishable = True
    session.commit()
    payload = client.get(f"/api/v1/extraction/runs/{run.id}/export").json()
    assert payload["status"] == status.value
    assert payload["publication"] is None
    assert previous.is_current is True
    assert graph.is_current is False


@pytest.mark.parametrize("unfinished", [True, False])
def test_unfinished_or_unpublished_run_has_no_manifest(
    client: TestClient, session: Session, unfinished: bool
) -> None:
    run, graph = make_run(session, RunResult.PARTIAL)
    if unfinished:
        run.finished_at = None
    else:
        graph.publishable = False
    session.commit()
    payload = client.get(f"/api/v1/extraction/runs/{run.id}/export").json()
    assert payload["publication"] is None


def test_export_allowlist_excludes_credentials_raw_errors_and_rows(
    client: TestClient, session: Session
) -> None:
    run, _ = make_run(session)
    secret = "not-a-real-password"
    run.cfg_snapshot = {
        "datasource_id": {"password": secret},
        "onto_version": True,
        "password": secret,
        "connection": {"url": f"postgresql://user:{secret}@example.org/db"},
        "samples": [{"raw_value": secret}],
    }
    run.counts = {
        "entity_count": secret,
        "triple_count": {"password": secret},
        "quarantine_count": True,
        "derived_edge_count": -1,
        "evidence_count": 0,
        "error": secret,
        "rows": [secret],
    }
    session.commit()
    response = client.get(f"/api/v1/extraction/runs/{run.id}/export")
    assert response.status_code == 200
    assert secret not in response.text
    payload = response.json()
    assert payload["datasource_id"] is None
    assert payload["ontology_revision"] is None
    assert payload["counts"] == {"evidence_count": 0}
    assert set(payload) == set(ExtractionRunExport.model_fields)


def test_legacy_missing_snapshot_is_not_backfilled(
    client: TestClient, session: Session
) -> None:
    run, _ = make_run(session)
    run.cfg_snapshot = {}
    run.counts = {"error": "internal-only"}
    session.commit()
    payload = client.get(f"/api/v1/extraction/runs/{run.id}/export").json()
    assert payload["ontology_revision"] is None  # 已有映射的 onto_version 仍不能补入。
    assert payload["datasource_id"] is None
    assert payload["counts"] == {}  # 缺失计数不伪装为 0。


def test_unknown_run_returns_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/extraction/runs/999/export")
    assert response.status_code == 404
    assert response.json()["code"] == "KG.RESOURCE_NOT_FOUND"
    assert response.json()["data"] is None
    assert "content-disposition" not in response.headers


def test_openapi_describes_download_without_envelope(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    response = spec["paths"]["/api/v1/extraction/runs/{run_id}/export"]["get"][
        "responses"
    ]["200"]
    assert response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ExtractionRunExport"
    }


def test_sqlite_new_session_download_preserves_utc(
    client: TestClient, session: Session
) -> None:
    run, _ = make_run(session)
    run_id = run.id
    engine = session.get_bind()

    def fresh_session() -> Iterator[Session]:
        with Session(engine) as db:
            yield db

    with Session(engine) as db:
        stored = db.get(ExtractionRun, run_id)
        assert stored is not None
        assert stored.started_at.tzinfo is None  # 真实 SQLite 落库回读。
    client.app.dependency_overrides[get_session] = fresh_session
    response = client.get(f"/api/v1/extraction/runs/{run_id}/export")
    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["started_at"] == "2026-09-23T01:00:00Z"
    assert payload["finished_at"] == "2026-09-23T02:00:00Z"
    assert payload["publication"]["published_at"] == "2026-09-23T02:00:00Z"
