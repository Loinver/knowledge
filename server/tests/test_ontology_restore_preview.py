"""完整导入的预览只读性、冲突与内容归属。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.core.db import Base
from app.domain.iri_service import register_namespace
from app.domain.ontology_restore_service import inspect_restore
from app.models.domain import Ontology
from app.models.enums import ResourceKind
from app.models.resource import ModelResource
from app.schemas.ontology import OntologyExportFormat
from app.semantics.ontology_rdf import (
    OntologyRdfMetadata,
    OntologyRdfResource,
    serialize_ontology_rdf,
)
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session


@pytest.fixture()
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path}/preview.sqlite")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def content() -> str:
    return serialize_ontology_rdf(
        OntologyRdfMetadata(
            name="RestoreExample",
            iri="https://example.org/ontology/restore",
            label_i18n={"zh-CN": "合成导入"},
            definition_i18n=None,
        ),
        {
            1: OntologyRdfResource(
                name="Employee",
                iri="https://example.org/kg#Employee",
                kind=ResourceKind.ENTITY,
                label_i18n={"zh-CN": "员工"},
                namespace={"prefix": "ex", "iri": "https://example.org/kg#"},
                parent_ids=[],
                resource_refs=[],
            )
        },
        revision=3,
        rdf_format=OntologyExportFormat.TURTLE,
    )


def test_preview_is_readonly_and_digest_tracks_source_and_database(
    session: Session,
) -> None:
    statements: list[str] = []

    def track(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _many: bool,
    ) -> None:
        statements.append(statement.lstrip().split()[0].upper())

    event.listen(session.get_bind(), "before_cursor_execute", track)
    _, before = inspect_restore(session, "turtle", content())
    assert before.can_apply, before.model_dump()
    assert before.source_revision == 3
    assert statements and set(statements) <= {"SELECT", "PRAGMA"}
    event.remove(session.get_bind(), "before_cursor_execute", track)
    _, changed = inspect_restore(session, "turtle", content() + "\n")
    assert before.preview_digest != changed.preview_digest
    ns = register_namespace(session, "ex", "https://example.org/kg#")
    session.add(
        ModelResource(
            name="Employee",
            iri="https://example.org/kg#Employee",
            kind=ResourceKind.ENTITY,
            namespace_id=ns.id,
        )
    )
    session.flush()
    _, conflict = inspect_restore(session, "turtle", content())
    assert not conflict.can_apply
    assert "RESOURCE_EXISTS" in {item.code for item in conflict.conflicts}
    assert conflict.preview_digest != before.preview_digest


def test_preview_reports_namespace_and_ontology_conflicts(session: Session) -> None:
    register_namespace(session, "ex", "https://example.org/other#")
    session.add(Ontology(name="RestoreExample", iri="https://example.org/other"))
    session.flush()
    _, preview = inspect_restore(session, "turtle", content())
    assert not preview.can_apply
    assert {item.code for item in preview.conflicts} >= {
        "ONTOLOGY_EXISTS",
        "NAMESPACE_PREFIX_CONFLICT",
    }
    assert session.scalar(select(func.count()).select_from(ModelResource)) == 0


def test_preview_exposes_unsupported_statements_without_applying_anything(
    session: Session,
) -> None:
    _, preview = inspect_restore(
        session,
        "turtle",
        content()
        + (
            "\n<https://example.org/kg#Employee> "
            '<https://example.org/externalRule> "opaque" .'
        ),
    )
    assert not preview.can_apply
    assert any("externalRule" in triple for triple in preview.unsupported_triples)
    assert session.scalar(select(func.count()).select_from(ModelResource)) == 0
