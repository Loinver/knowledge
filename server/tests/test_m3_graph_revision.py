"""图谱版本与结果集管理（H-33）。

A20 运行闭环验收：
- 前置校验拦截（草稿不能运行）
- 零产出判失败
- 失败不覆盖上一成功版本
- 结果集可切换
- 版本列表含历史
- is_current 唯一性（部分唯一索引兜底）
"""

from __future__ import annotations

import pytest
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.extraction_service import (
    get_current_graph,
    list_graph_revisions,
    start_run,
    switch_current,
)
from app.domain.mapping_service import (
    create_mapping,
    publish_mapping,
    save_draft,
)
from app.domain.metadata_service import capture_metadata
from app.domain.source_service import create_datasource
from app.models.data_access import MappingRevision
from app.models.domain import Ontology, OntologyRevision
from app.models.enums import RunResult
from app.schemas.datasource import DatasourceCreate
from app.schemas.mapping import (
    EntityMapCreate,
    FieldMap,
    MappingCreate,
    MappingRevisionCreate,
    RelMode,
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker


def _make_source(path: str) -> None:
    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as conn:
        conn.execute(
            text("CREATE TABLE enterprise (id INTEGER PRIMARY KEY, name TEXT)")
        )
        conn.execute(
            text(
                "INSERT INTO enterprise (id, name) VALUES "
                "(1001, '企业A'), (1002, '企业B')"
            )
        )
        conn.execute(text("CREATE TABLE ghost_empty (id INTEGER PRIMARY KEY)"))
        conn.commit()


@pytest.fixture()
def session(tmp_path):
    url = f"sqlite:///{tmp_path}/kg.db"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    sess = sf()
    yield sess
    sess.close()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def source_db(tmp_path):
    path = str(tmp_path / "src.db")
    _make_source(path)
    yield path


def _setup_onto(session):
    onto = Ontology(
        name="o1",
        iri="https://example.org/o1#",
        status="PUBLISHED",
        current_revision=1,
    )
    session.add(onto)
    session.flush()
    rev = OntologyRevision(
        ontology_id=onto.id,
        revision=1,
        ref_domains=[],
        ref_types=[],
        rules=[],
        resource_versions={},
    )
    session.add(rev)
    session.flush()
    return onto


def _setup_ds(session, source_db):
    ds = create_datasource(
        session,
        DatasourceCreate(name="ds1", kind="sqlite", params={"database": source_db}),
    )
    session.commit()
    capture_metadata(session, ds.id)
    session.commit()
    return ds


def _good_mapping(session, onto):
    m = create_mapping(session, MappingCreate(name="good", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="Enterprise",
                    table="enterprise",
                    field_maps=[FieldMap(target_attr="name", source_field="name")],
                    key_fields=["id"],
                )
            ],
            rel_maps=[],
        ),
        if_match=0,
    )
    session.commit()
    rev = publish_mapping(session, m.id, if_match=0)
    session.commit()
    return rev


def _empty_mapping(session, onto):
    """映射到空表，零产出。"""
    m = create_mapping(session, MappingCreate(name="empty", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="Ghost",
                    table="ghost_empty",
                    field_maps=[FieldMap(target_attr="x", source_field="x")],
                    key_fields=["id"],
                )
            ],
            rel_maps=[],
        ),
        if_match=0,
    )
    session.commit()
    rev = publish_mapping(session, m.id, if_match=0)
    session.commit()
    return rev


def test_draft_cannot_run(session, source_db):
    """A20-1：前置校验拦截——草稿 revision 不能运行。"""
    onto = _setup_onto(session)
    _setup_ds(session, source_db)
    m = create_mapping(session, MappingCreate(name="draft", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="E",
                    table="enterprise",
                    field_maps=[FieldMap(target_attr="n", source_field="name")],
                    key_fields=["id"],
                )
            ],
            rel_maps=[],
        ),
        if_match=0,
    )
    session.commit()
    draft_rev = (
        session.query(MappingRevision)
        .filter(
            MappingRevision.mapping_id == m.id,
            MappingRevision.revision == 0,
        )
        .first()
    )
    with pytest.raises(KGError) as exc:
        start_run(session, draft_rev.id, 1)
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION


def test_zero_output_failed(session, source_db):
    """A20-2：零产出判 FAILED。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    rev = _empty_mapping(session, onto)
    run = start_run(session, rev.id, ds.id)
    session.commit()
    assert run.status == RunResult.FAILED
    assert run.counts.get("entity_count", 0) == 0


def test_failure_does_not_overwrite_current(session, source_db):
    """A20-3：失败运行不覆盖上一成功版本。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)

    # 第一次成功运行
    good_rev = _good_mapping(session, onto)
    start_run(session, good_rev.id, ds.id)
    session.commit()
    gr_ok = get_current_graph(session)
    assert gr_ok is not None
    assert gr_ok.is_current is True

    # 第二次失败运行（空表）
    empty_rev = _empty_mapping(session, onto)
    run_fail = start_run(session, empty_rev.id, ds.id)
    session.commit()
    assert run_fail.status == RunResult.FAILED

    # is_current 仍指向成功版本
    gr_now = get_current_graph(session)
    assert gr_now is not None
    assert gr_now.id == gr_ok.id


def test_result_set_switchable(session, source_db):
    """A20-4：结果集可切换——历史成功运行切回。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    rev = _good_mapping(session, onto)

    start_run(session, rev.id, ds.id)
    session.commit()
    gr1 = get_current_graph(session)
    assert gr1 is not None

    start_run(session, rev.id, ds.id)
    session.commit()
    gr2 = get_current_graph(session)
    assert gr2 is not None
    assert gr2.id != gr1.id

    switched = switch_current(session, gr1.id)
    session.commit()
    assert switched.id == gr1.id
    assert switched.is_current is True
    assert get_current_graph(session).id == gr1.id


def test_cannot_switch_failed_run(session, source_db):
    """失败运行的 graph_revision 不能切为 current。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    empty_rev = _empty_mapping(session, onto)
    run = start_run(session, empty_rev.id, ds.id)
    session.commit()
    assert run.status == RunResult.FAILED

    from app.models.extraction import GraphRevision

    failed_gr = (
        session.query(GraphRevision).filter(GraphRevision.run_id == run.id).first()
    )
    with pytest.raises(KGError) as exc:
        switch_current(session, failed_gr.id)
    assert exc.value.code == ErrorCode.VALIDATION_VIOLATION


def test_version_list_includes_history(session, source_db):
    """版本列表含历史成功运行。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    rev = _good_mapping(session, onto)

    start_run(session, rev.id, ds.id)
    session.commit()
    start_run(session, rev.id, ds.id)
    session.commit()
    start_run(session, rev.id, ds.id)
    session.commit()

    revisions, total = list_graph_revisions(session)
    assert total == 3
    assert len(revisions) == 3
    # 只有一个 is_current
    current_count = sum(1 for r in revisions if r.is_current)
    assert current_count == 1


def test_is_current_uniqueness(session, source_db):
    """is_current 部分唯一索引：同一时刻只有一个 True。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    rev = _good_mapping(session, onto)

    start_run(session, rev.id, ds.id)
    session.commit()
    start_run(session, rev.id, ds.id)
    session.commit()

    revisions, _ = list_graph_revisions(session)
    current = [r for r in revisions if r.is_current]
    assert len(current) == 1


def test_relation_mode_validation():
    """RelMode 枚举三值。"""
    assert RelMode.FK == "FK"
    assert RelMode.JUNCTION == "JUNCTION"
    assert RelMode.ASSOCIATIVE == "ASSOCIATIVE"
