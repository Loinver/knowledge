"""PC09: real SQLite transactions across processes, including ordinary writers."""

from __future__ import annotations

import multiprocessing
from collections.abc import Iterator
from multiprocessing.connection import Connection
from pathlib import Path

import pytest
from app.core.db import Base
from app.core.errors import KGError
from app.domain import ontology_restore_service
from app.domain.iri_service import register_namespace
from app.domain.ontology_restore_service import inspect_restore, restore_ontology
from app.domain.ontology_service import create_ontology
from app.models.domain import Ontology
from app.models.resource import ModelResource, Namespace, ResourceRevision
from app.schemas.ontology import OntologyCreate
from app.schemas.ontology_import import ImportFormat
from app.schemas.ontology_restore import OntologyRestorePreview, OntologyRestoreRequest
from app.semantics.ontology_restore import RestoreDocument
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from test_ontology_restore_preview import content


@pytest.fixture(params=["DELETE", "WAL"])
def engine(tmp_path: Path, request: pytest.FixtureRequest) -> Iterator[Engine]:
    database = create_engine(f"sqlite:///{tmp_path}/concurrent.sqlite")
    with database.connect() as connection:
        mode = connection.scalar(text(f"PRAGMA journal_mode={request.param}"))
        assert str(mode).upper() == request.param
    Base.metadata.create_all(database)
    yield database
    database.dispose()


def request_for(engine: Engine, source: str) -> OntologyRestoreRequest:
    with Session(engine) as session:
        _, preview = inspect_restore(session, "turtle", source)
        assert preview.can_apply
        return OntologyRestoreRequest(
            format="turtle", content=source, preview_digest=preview.preview_digest
        )


def competing_write(
    url: str, mode: str, payload: dict[str, object], result: Connection
) -> None:
    """Use a new process/engine; no shared connection or Python locking."""
    engine = create_engine(url, connect_args={"timeout": 0.2})
    try:
        with Session(engine) as session:
            try:
                if mode == "namespace":
                    register_namespace(session, "ex", "https://example.org/other#")
                elif mode == "ontology":
                    create_ontology(
                        session,
                        OntologyCreate(
                            name="ConcurrentOntology",
                            iri="https://example.org/ontology/restore",
                            label_i18n={},
                        ),
                    )
                else:
                    restore_ontology(
                        session, OntologyRestoreRequest.model_validate(payload)
                    )
                session.commit()
                result.send(("committed", ""))
            except KGError as exc:
                session.rollback()
                result.send(("rejected", str(exc.code)))
            except OperationalError as exc:
                session.rollback()
                result.send(("locked", str(exc.orig)))
    finally:
        result.close()
        engine.dispose()


def run_competitor(
    engine: Engine, mode: str, payload: OntologyRestoreRequest
) -> tuple[str, str]:
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(
        target=competing_write,
        args=(str(engine.url), mode, payload.model_dump(), send),
    )
    process.start()
    send.close()
    try:
        assert receive.poll(15), "competing process did not finish"
        result: tuple[str, str] = receive.recv()
        process.join(5)
        assert process.exitcode == 0
        return result
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
        receive.close()
        process.close()


@pytest.mark.parametrize("mode", ["namespace", "ontology", "restore"])
def test_writer_cannot_commit_between_restore_recheck_and_api_commit(
    engine: Engine, mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = request_for(engine, content())
    # Different names, resources and namespaces: only the ontology IRI overlaps.
    other = request_for(
        engine,
        content()
        .replace("RestoreExample", "OtherRestore")
        .replace("Employee", "Customer")
        .replace("https://example.org/kg#", "https://example.org/second#")
        .replace('"ex"', '"other"'),
    )
    original = inspect_restore
    outcomes: list[tuple[str, str]] = []

    def inspect_and_compete(
        session: Session, rdf_format: ImportFormat, source: str
    ) -> tuple[RestoreDocument, OntologyRestorePreview]:
        reviewed = original(session, rdf_format, source)
        assert reviewed[1].can_apply
        outcomes.append(run_competitor(engine, mode, other))
        return reviewed

    monkeypatch.setattr(
        ontology_restore_service, "inspect_restore", inspect_and_compete
    )
    with Session(engine) as session:
        restored = restore_ontology(session, payload)
        # The service neither commits nor releases its lock on return.
        outcomes.append(run_competitor(engine, mode, other))
        with Session(engine) as observer:
            assert observer.scalar(select(func.count()).select_from(Ontology)) == 0
        session.commit()
        assert restored.current_revision == 1

    if mode == "restore":
        assert outcomes == [("rejected", "KG.REVISION_CONFLICT")] * 2
    else:
        assert all(state == "locked" and "locked" in error for state, error in outcomes)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Ontology)) == 1
        resource = session.scalar(select(ModelResource))
        assert resource is not None
        namespace = session.get(Namespace, resource.namespace_id)
        assert namespace is not None and namespace.iri == "https://example.org/kg#"
        revision = session.scalar(select(ResourceRevision))
        assert revision is not None
        assert revision.payload["namespace"]["iri"] == namespace.iri
        assert revision.payload["iri"] == resource.iri == namespace.iri + resource.name
    # A later restore must also detect the committed IRI under its own lock.
    if mode == "restore":
        assert run_competitor(engine, mode, other) == (
            "rejected",
            "KG.REVISION_CONFLICT",
        )


@pytest.mark.parametrize("mode", ["namespace", "ontology"])
def test_restore_rechecks_a_competing_commit_since_preview(
    engine: Engine, mode: str
) -> None:
    payload = request_for(engine, content())
    assert run_competitor(engine, mode, payload) == ("committed", "")
    with Session(engine) as session:
        with pytest.raises(KGError) as caught:
            restore_ontology(session, payload)
        session.rollback()
        assert str(caught.value.code) == "KG.REVISION_CONFLICT"
        assert session.scalar(select(func.count()).select_from(ModelResource)) == 0
        assert session.scalar(select(func.count()).select_from(ResourceRevision)) == 0
        assert session.scalar(select(func.count()).select_from(Ontology)) == (
            1 if mode == "ontology" else 0
        )


def test_restore_lock_contention_rolls_back_and_can_retry(engine: Engine) -> None:
    payload = request_for(engine, content())
    with Session(engine) as writer:
        create_ontology(
            writer,
            OntologyCreate(
                name="Unrelated", iri="https://example.org/unrelated", label_i18n={}
            ),
        )
        assert run_competitor(engine, "restore", payload) == (
            "rejected",
            "KG.REVISION_CONFLICT",
        )
        writer.rollback()
    assert run_competitor(engine, "restore", payload) == ("committed", "")
