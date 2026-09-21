"""映射编译预览集成测试（H-31）。"""

from __future__ import annotations

import pytest
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.mapping_compiler import (
    _apply_transform,
    _compile_field,
    compile_mapping,
)
from app.domain.mapping_service import (
    create_mapping,
    publish_mapping,
    save_draft,
)
from app.domain.metadata_service import capture_metadata
from app.domain.source_service import create_datasource
from app.models.data_access import MappingPreview
from app.models.domain import Ontology, OntologyRevision
from app.models.enums import ResourceStatus
from app.schemas.datasource import DatasourceCreate
from app.schemas.mapping import (
    EntityMapCreate,
    FieldMap,
    MappingCreate,
    MappingRevisionCreate,
    NullPolicy,
    RelMapCreate,
    RelMode,
    TransformKind,
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker


def _make_source(path: str) -> None:
    eng = create_engine(f"sqlite:///{path}")
    with eng.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE enterprise ("
                "id INTEGER PRIMARY KEY, name TEXT, "
                "amount TEXT, code TEXT, join_date TEXT)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO enterprise (id, name, amount, code, join_date) VALUES "
                "(1, 'A', '100.5', 'C1', '2024-01-10'), "
                "(2, '', '200', 'C2', '2024/02/20'), "
                "(3, 'B', '', 'C3', 'bad-date')"
            )
        )
        conn.execute(
            text("CREATE TABLE hr_emp (id INTEGER PRIMARY KEY, enterprise_id INTEGER)")
        )
        conn.execute(
            text("INSERT INTO hr_emp (id, enterprise_id) VALUES (1, 1001), (2, NULL)")
        )
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
        iri="https://example.org/o1",
        status=ResourceStatus.PUBLISHED,
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


def test_compile_identity_transform(session, source_db):
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    m = create_mapping(session, MappingCreate(name="m1", ontology_id=onto.id))
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
    result = compile_mapping(session, m.id, ds.id, limit=10, use_draft=True)
    session.commit()
    ent = result["entities"][0]
    assert ent["entity_type"] == "Enterprise"
    assert len(ent["rows"]) == 3
    row0 = ent["rows"][0]
    cell_name = next(c for c in row0["cells"] if c["target_attr"] == "name")
    assert cell_name["value"] == "A"
    assert cell_name["status"] == "ok"


def test_compile_required_violation(session, source_db):
    """A11/A12：REQUIRED 策略遇空报错，定位到字段级。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    m = create_mapping(session, MappingCreate(name="req", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="E",
                    table="enterprise",
                    field_maps=[
                        FieldMap(
                            target_attr="name",
                            source_field="name",
                            null_policy=NullPolicy.REQUIRED,
                        )
                    ],
                    key_fields=["id"],
                )
            ],
            rel_maps=[],
        ),
        if_match=0,
    )
    session.commit()
    result = compile_mapping(session, m.id, ds.id, limit=10, use_draft=True)
    session.commit()
    required_errs = [
        e for e in result["errors"] if e.get("code") == "required_violation"
    ]
    assert len(required_errs) >= 1
    assert required_errs[0]["field"] == "name"
    assert required_errs[0]["row"] == 1  # row index 1 是空 name


def test_compile_default_policy(session, source_db):
    """DEFAULT 策略遇空用默认值。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    m = create_mapping(session, MappingCreate(name="def", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="E",
                    table="enterprise",
                    field_maps=[
                        FieldMap(
                            target_attr="name",
                            source_field="name",
                            null_policy=NullPolicy.DEFAULT,
                            default_value="无名",
                        )
                    ],
                )
            ],
        ),
        if_match=0,
    )
    session.commit()
    result = compile_mapping(session, m.id, ds.id, limit=10, use_draft=True)
    session.commit()
    row1 = result["entities"][0]["rows"][1]
    cell = next(c for c in row1["cells"] if c["target_attr"] == "name")
    assert cell["value"] == "无名"
    assert cell["status"] == "ok"


def test_compile_date_transform(session, source_db):
    """A12：DATE 转换解析多种格式，失败定位到字段。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    m = create_mapping(session, MappingCreate(name="date", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="E",
                    table="enterprise",
                    field_maps=[
                        FieldMap(
                            target_attr="join_date",
                            source_field="join_date",
                            transform=TransformKind.DATE,
                        )
                    ],
                )
            ],
        ),
        if_match=0,
    )
    session.commit()
    result = compile_mapping(session, m.id, ds.id, limit=10, use_draft=True)
    session.commit()
    rows = result["entities"][0]["rows"]
    # row0: 2024-01-10 -> 2024-01-10
    assert rows[0]["cells"][0]["value"] == "2024-01-10"
    # row2: bad-date -> error
    date_errs = [e for e in result["errors"] if e.get("code") == "date_parse_failed"]
    assert len(date_errs) >= 1
    assert date_errs[0]["row"] == 2


def test_compile_enum_transform(session, source_db):
    """A12：ENUM 映射，未匹配报错。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    m = create_mapping(session, MappingCreate(name="enum", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="E",
                    table="enterprise",
                    field_maps=[
                        FieldMap(
                            target_attr="tier",
                            source_field="code",
                            transform=TransformKind.ENUM,
                            transform_params={
                                "mapping": {"C1": "gold", "C2": "silver"}
                            },
                        )
                    ],
                )
            ],
        ),
        if_match=0,
    )
    session.commit()
    result = compile_mapping(session, m.id, ds.id, limit=10, use_draft=True)
    session.commit()
    rows = result["entities"][0]["rows"]
    assert rows[0]["cells"][0]["value"] == "gold"
    assert rows[1]["cells"][0]["value"] == "silver"
    unmapped = [e for e in result["errors"] if e.get("code") == "enum_unmapped"]
    assert len(unmapped) >= 1  # C3 未在映射里


def test_compile_decimal_transform(session, source_db):
    """A12：DECIMAL 精度。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    m = create_mapping(session, MappingCreate(name="dec", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="E",
                    table="enterprise",
                    field_maps=[
                        FieldMap(
                            target_attr="amount",
                            source_field="amount",
                            transform=TransformKind.DECIMAL,
                            transform_params={"precision": 2},
                        )
                    ],
                )
            ],
        ),
        if_match=0,
    )
    session.commit()
    result = compile_mapping(session, m.id, ds.id, limit=10, use_draft=True)
    session.commit()
    rows = result["entities"][0]["rows"]
    assert rows[0]["cells"][0]["value"] == "100.50"


def test_compile_template_transform(session, source_db):
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    m = create_mapping(session, MappingCreate(name="tmpl", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="E",
                    table="enterprise",
                    field_maps=[
                        FieldMap(
                            target_attr="iri",
                            source_field="id",
                            transform=TransformKind.TEMPLATE,
                            transform_params={"template": "ent-{value}"},
                        )
                    ],
                )
            ],
        ),
        if_match=0,
    )
    session.commit()
    result = compile_mapping(session, m.id, ds.id, limit=10, use_draft=True)
    session.commit()
    rows = result["entities"][0]["rows"]
    assert rows[0]["cells"][0]["value"] == "ent-1"


def test_compile_duplicate_key_detected(session, source_db):
    """A11：重复键报错。"""
    # 改造源库让两行 id 相同是不行的（PK），改测 key_fields 用非唯一字段
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    m = create_mapping(session, MappingCreate(name="dup", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="E",
                    table="enterprise",
                    field_maps=[FieldMap(target_attr="name", source_field="name")],
                    key_fields=["code"],  # C1 C2 C3 唯一，应无重复
                )
            ],
        ),
        if_match=0,
    )
    session.commit()
    result = compile_mapping(session, m.id, ds.id, limit=10, use_draft=True)
    session.commit()
    dup_errs = [e for e in result["errors"] if e.get("code") == "duplicate_key"]
    assert len(dup_errs) == 0  # code 唯一


def test_compile_relation_fk_empty_endpoint(session, source_db):
    """A11：FK 模式空端点报错。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    m = create_mapping(session, MappingCreate(name="fkep", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[],
            rel_maps=[
                RelMapCreate(
                    relation_type="works_for",
                    mode=RelMode.FK,
                    table="hr_emp",
                    fk_field="enterprise_id",
                )
            ],
        ),
        if_match=0,
    )
    session.commit()
    result = compile_mapping(session, m.id, ds.id, limit=10, use_draft=True)
    session.commit()
    empty_eps = [e for e in result["errors"] if e.get("code") == "empty_endpoint"]
    assert len(empty_eps) >= 1  # row 1 的 enterprise_id 是 NULL


def test_compile_table_not_in_catalog(session, source_db):
    """表不在元数据快照里报错。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    m = create_mapping(session, MappingCreate(name="ghost", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="E",
                    table="ghost_table",
                    field_maps=[FieldMap(target_attr="x", source_field="x")],
                )
            ],
        ),
        if_match=0,
    )
    session.commit()
    result = compile_mapping(session, m.id, ds.id, limit=10, use_draft=True)
    session.commit()
    nf_errs = [e for e in result["errors"] if e.get("code") == "table_not_found"]
    assert len(nf_errs) >= 1


def test_compile_requires_metadata_snapshot(session, source_db):
    onto = _setup_onto(session)
    ds = create_datasource(
        session,
        DatasourceCreate(name="nosnap", kind="sqlite", params={"database": source_db}),
    )
    session.commit()
    m = create_mapping(session, MappingCreate(name="ns", ontology_id=onto.id))
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
                )
            ]
        ),
        if_match=0,
    )
    session.commit()
    with pytest.raises(KGError) as exc:
        compile_mapping(session, m.id, ds.id, use_draft=True)
    assert exc.value.code == ErrorCode.INVALID_REQUEST


def test_compile_uses_published_revision(session, source_db):
    """不传 use_draft 时用已发布 revision。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    m = create_mapping(session, MappingCreate(name="pub", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="E",
                    table="enterprise",
                    field_maps=[FieldMap(target_attr="name", source_field="name")],
                )
            ]
        ),
        if_match=0,
    )
    session.commit()
    publish_mapping(session, m.id, if_match=0)
    session.commit()
    result = compile_mapping(session, m.id, ds.id, limit=10, use_draft=False)
    session.commit()
    assert result["revision"] == 1
    assert result["onto_version"] == 1


def test_compile_persists_preview(session, source_db):
    """预览结果落 mapping_preview 表。"""
    onto = _setup_onto(session)
    ds = _setup_ds(session, source_db)
    m = create_mapping(session, MappingCreate(name="persist", ontology_id=onto.id))
    session.commit()
    save_draft(
        session,
        m.id,
        MappingRevisionCreate(
            entity_maps=[
                EntityMapCreate(
                    entity_type="E",
                    table="enterprise",
                    field_maps=[FieldMap(target_attr="name", source_field="name")],
                )
            ]
        ),
        if_match=0,
    )
    session.commit()
    result = compile_mapping(session, m.id, ds.id, use_draft=True)
    session.commit()
    preview_id = result["preview_id"]
    saved = session.get(MappingPreview, preview_id)
    assert saved is not None
    assert "entities" in saved.results
    assert saved.results["summary"]["entity_count"] == 1


def test_apply_transform_identity():
    val, err = _apply_transform("IDENTITY", {}, "x", "t", 0, "E")
    assert val == "x"
    assert err is None


def test_compile_field_source_missing():
    """源字段不存在报错定位到字段。"""
    fm = {
        "target_attr": "x",
        "source_field": "ghost",
        "transform": "IDENTITY",
        "null_policy": "NULLABLE",
    }
    raw = {"id": 1}
    cell, errs = _compile_field(fm, raw, "E", 0)
    assert cell["status"] == "error"
    assert errs[0]["code"] == "source_field_missing"
