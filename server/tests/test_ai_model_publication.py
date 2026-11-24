"""Model selection and index publication have one transaction ordering."""

from __future__ import annotations

import json
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event, current_thread
from typing import Any

import pytest
from app.core.db import bound_scope
from app.domain import ai_model_service, knowledge_service
from app.models.ai_model import AiModelDefault
from app.schemas.ai_model import AiModelConfigUpdate
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

import test_knowledge_service as ingestion
from ai_model_helpers import embedding_response, mock_transport, seed_model

factory = ingestion.factory


@pytest.mark.parametrize("selected", [False, True])
def test_configuration_commit_before_publication_preserves_active_index(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch, selected: bool
) -> None:
    document = ingestion.upload(factory)
    ingestion.process(factory)
    before = ingestion.output(factory, document.id)
    with bound_scope(factory) as session:
        model_id = seed_model(session).id if selected else None
        knowledge_service.queue_document(session, 1, document.id, before.revision)
    mock_transport(
        monkeypatch,
        lambda request: embedding_response(
            [[1.0, 0.0] for _ in json.loads(request.content)["input"]]
        ),
    )
    original = ai_model_service.lock_default_for_publication

    def change_before_lock(
        session: Session,
        capability: ai_model_service.CapabilityValue,
        resolved: ai_model_service.ResolvedModel | None,
    ) -> None:
        with bound_scope(factory) as other:
            if model_id is None:
                seed_model(other)
            else:
                ai_model_service.update_config(
                    other, model_id, AiModelConfigUpdate(model_version="changed"), 1
                )
        original(session, capability, resolved)

    monkeypatch.setattr(
        ai_model_service, "lock_default_for_publication", change_before_lock
    )
    ingestion.process(factory)
    after = ingestion.output(factory, document.id)
    assert after.active_generation == before.active_generation
    assert after.latest_task is not None and after.latest_task.status == "FAILED"
    assert after.latest_task.error_code == "KG.REVISION_CONFLICT"
    assert after.latest_task.error_reason == "model_configuration_changed"


@pytest.mark.parametrize("selected", [False, True])
def test_publication_lock_serializes_configuration_writer_until_commit(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch, selected: bool
) -> None:
    document = ingestion.upload(factory)
    ingestion.process(factory)
    before = ingestion.output(factory, document.id)
    with bound_scope(factory) as session:
        model_id = seed_model(session).id if selected else None
        knowledge_service.queue_document(session, 1, document.id, before.revision)
    mock_transport(
        monkeypatch,
        lambda request: embedding_response(
            [[1.0, 0.0] for _ in json.loads(request.content)["input"]]
        ),
    )
    attempting_write, committed = Event(), Event()
    original = knowledge_service.publish_index
    futures: list[Future[None]] = []
    with factory() as probe:
        engine = probe.get_bind().engine

    def observe_write(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if current_thread().name.startswith(
            "model-writer"
        ) and statement.lower().startswith(
            ("update ai_model_config", "insert into ai_model_config")
        ):
            attempting_write.set()

    def change_configuration() -> None:
        with bound_scope(factory) as other:
            if model_id is None:
                seed_model(other)
            else:
                ai_model_service.update_config(
                    other,
                    model_id,
                    AiModelConfigUpdate(model_version="after-commit"),
                    1,
                )
        committed.set()

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="model-writer") as pool:

        def publish_with_competing_writer(
            session: Session,
            claim: knowledge_service.ClaimedTask,
            index_id: str,
            vectors: list[list[float]] | None,
            **kwargs: Any,
        ) -> bool:
            futures.append(pool.submit(change_configuration))
            assert attempting_write.wait(3), (
                "The competing writer reached its SQL write"
            )
            assert not committed.wait(0.05), (
                "Configuration cannot commit inside publication"
            )
            return original(session, claim, index_id, vectors, **kwargs)

        event.listen(engine, "before_cursor_execute", observe_write)
        monkeypatch.setattr(
            knowledge_service, "publish_index", publish_with_competing_writer
        )
        try:
            ingestion.process(factory)
            assert len(futures) == 1
            futures[0].result(timeout=5)
        finally:
            event.remove(engine, "before_cursor_execute", observe_write)
    assert committed.is_set()
    after = ingestion.output(factory, document.id)
    assert after.active_generation != before.active_generation
    assert after.latest_task is not None and after.latest_task.status == "SUCCESS"


def test_publication_lock_preserves_configuration_revision_and_timestamp(
    factory: sessionmaker[Session],
) -> None:
    with bound_scope(factory) as session:
        seed_model(session)
        resolved = ai_model_service.resolve_default(session, "EMBEDDING")
        selection = session.get(AiModelDefault, "EMBEDDING")
        assert selection is not None
        previous = (selection.revision, selection.updated_at, selection.config_id)
    with bound_scope(factory) as session:
        ai_model_service.lock_default_for_publication(session, "EMBEDDING", resolved)
    with factory() as session:
        selection = session.get(AiModelDefault, "EMBEDDING")
        assert selection is not None
        assert (
            selection.revision,
            selection.updated_at,
            selection.config_id,
        ) == previous
