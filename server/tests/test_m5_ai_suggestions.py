"""AI 建议服务测试（第三批 V-DS-05 / V-EX-07）。

必测断言：
- 未配置 LLM → KG.LLM_NOT_CONFIGURED，绝不内置模拟回复
- 建议生成：无效项被丢弃，只保留类型/列校验通过的 PENDING 建议
- 应用：只写草稿资产；已发布资源/已发布映射/仅审阅类如实拒绝
- 忽略：PENDING → DISCARDED，不可重复处理
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.ai_model_service import resolve_default
from app.domain.ai_suggestion_service import (
    apply_suggestion,
    discard_suggestion,
    extract_document_facts,
    list_suggestions,
    suggest_mapping,
    suggest_ontology_completion,
)
from app.domain.mapping_service import create_mapping, get_draft_revision, save_draft
from app.domain.metadata_service import capture_metadata, get_latest_snapshot
from app.domain.ontology_service import publish_ontology
from app.domain.source_service import create_datasource
from app.domain.status_service import publish_resource
from app.domain.type_service import create_entity_type, set_data_props
from app.models.account import User
from app.models.ai_model import AiModelCapability, AiModelDefault
from app.models.domain import Ontology
from app.models.enums import ResourceKind, ResourceStatus, UserRole
from app.models.governance import AiSuggestion
from app.models.resource import ResourceParent
from app.schemas.datasource import DatasourceCreate
from app.schemas.mapping import MappingCreate, MappingRevisionCreate
from app.schemas.type import DataTypePropCreate, EntityTypeCreate
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from ai_model_helpers import FAKE_KEY, stub_chat_json


@pytest.fixture()
def session(tmp_path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path}/ai.db")
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False)
    sess = sf()
    sess.add(
        User(
            username="ai_admin",
            email="ai@example.org",
            password_hash="x",
            role=UserRole.ADMIN,
        )
    )
    onto = Ontology(
        name="ai-onto",
        iri="https://example.org/ai/onto/",
        label_i18n={"zh-CN": "AI 本体"},
    )
    sess.add(onto)
    sess.commit()
    yield sess
    sess.close()
    Base.metadata.drop_all(engine)


def _attach(session: Session, resource_id: int) -> None:
    """把资源挂进测试本体（建议上下文只看本体引用）。"""
    from app.domain.ontology_service import OntologyRefAdd, add_ref
    from app.models.domain import Ontology

    onto = session.query(Ontology).first()
    assert onto is not None
    add_ref(session, onto.id, OntologyRefAdd(resource_id=resource_id))
    session.commit()


def _onto_id(session: Session) -> int:
    from app.models.domain import Ontology

    onto = session.query(Ontology).first()
    assert onto is not None
    return onto.id


def _entity(
    session: Session,
    name: str,
    published: bool = False,
    with_name_property: bool = False,
):
    from app.domain.iri_service import register_namespace
    from app.models.resource import Namespace

    ns = session.query(Namespace).filter_by(prefix="ai").one_or_none()
    if ns is None:
        ns = register_namespace(session, "ai", "https://example.org/ai#")
    res = create_entity_type(
        session,
        EntityTypeCreate(
            name=name,
            namespace_id=ns.id,
            label_i18n={"en-US": name},
            data_props=(
                [DataTypePropCreate(name="name", datatype="string")]
                if with_name_property
                else []
            ),
        ),
    )
    if published:
        publish_resource(session, res)
    session.commit()
    _attach(session, res.id)
    return res


def test_unconfigured_llm_returns_structured_error(session: Session) -> None:
    from app.models.domain import Ontology

    onto = session.query(Ontology).first()
    assert onto is not None
    assert (
        session.scalar(
            select(AiModelDefault.config_id).where(
                AiModelDefault.capability == AiModelCapability.CHAT
            )
        )
        is None
    )
    with pytest.raises(KGError) as exc_info:
        suggest_ontology_completion(session, onto.id)
    assert exc_info.value.code is ErrorCode.LLM_NOT_CONFIGURED


def _assert_selected_model(session: Session, items: list[AiSuggestion]) -> None:
    selected = resolve_default(session, AiModelCapability.CHAT)
    assert selected is not None and items
    for item in items:
        assert item.payload["_model"] == {
            "config_id": selected.config_id,
            "config_revision": selected.config_revision,
            "default_revision": selected.default_revision,
            "model": selected.endpoint.model,
            "model_version": selected.model_version,
        }
        dumped = json.dumps(item.payload)
        assert FAKE_KEY not in dumped
        assert "credential_cipher" not in dumped and "api_key" not in dumped


def test_completion_suggestions_apply_to_draft(session: Session, monkeypatch) -> None:
    res = _entity(session, "Employee")
    payloads = [
        {
            "resource_id": res.id,
            "label_zh": "员工",
            "label_en": "Employee",
            "definition_zh": "受雇于组织的人员",
            "definition_en": "A person employed by an organization",
            "explanation": "基于资源名推断",
        }
    ]
    stub_chat_json(session, monkeypatch, lambda system, user: payloads)

    items = suggest_ontology_completion(session, _onto_id(session))
    assert len(items) == 1
    _assert_selected_model(session, items)
    assert items[0].status == "PENDING"
    applied = apply_suggestion(session, items[0].id)
    assert applied.status == "APPLIED"
    session.expire(res)
    assert res.label_i18n["zh-CN"] == "员工"
    assert res.definition_i18n["en-US"] == "A person employed by an organization"


def test_completion_skips_invalid_items(session: Session, monkeypatch) -> None:
    res = _entity(session, "Employee")
    payloads = [
        {"resource_id": res.id, "label_zh": "员工", "explanation": "ok"},
        {"resource_id": res.id, "label_zh": "", "explanation": "空标签被丢弃"},
        {"resource_id": 99999, "label_zh": "未知资源", "explanation": "未知资源被丢弃"},
        {"label_zh": "缺资源ID", "explanation": "缺资源ID被丢弃"},
    ]
    stub_chat_json(session, monkeypatch, lambda system, user: payloads)
    items = suggest_ontology_completion(session, _onto_id(session))
    assert len(items) == 1


def test_cannot_apply_to_published_resource(session: Session, monkeypatch) -> None:
    res = _entity(session, "Enterprise", published=True)
    stub_chat_json(
        session,
        monkeypatch,
        lambda system, user: [
            {"resource_id": res.id, "label_zh": "企业", "explanation": ""}
        ],
    )
    items = suggest_ontology_completion(session, _onto_id(session))
    assert items == []


def test_discard_marks_and_rejects_repeat(session: Session, monkeypatch) -> None:
    res = _entity(session, "Person")
    stub_chat_json(
        session,
        monkeypatch,
        lambda system, user: [
            {"resource_id": res.id, "label_zh": "人员", "explanation": ""}
        ],
    )
    items = suggest_ontology_completion(session, _onto_id(session))
    discarded = discard_suggestion(session, items[0].id)
    assert discarded.status == "DISCARDED"
    with pytest.raises(KGError):
        discard_suggestion(session, items[0].id)
    pending = list_suggestions(session, status="PENDING")
    assert pending == []


def test_document_facts_review_only(session: Session, monkeypatch) -> None:
    _entity(session, "Person")
    _entity(session, "Enterprise")
    stub_chat_json(
        session,
        monkeypatch,
        lambda system, user: [
            {
                "subject_type": "Person",
                "subject_name": "张三",
                "predicate": "",
                "object_type": "Enterprise",
                "object_name": "示例企业",
                "evidence": "张三入职示例企业",
                "explanation": "从句子抽取",
            },
            {
                "subject_type": "Unknown",
                "subject_name": "李四",
                "predicate": "",
                "object_type": "Enterprise",
                "object_name": "示例企业",
                "evidence": "未知类型被丢弃",
                "explanation": "",
            },
        ],
    )
    items = extract_document_facts(session, _onto_id(session), "张三入职示例企业。")
    assert len(items) == 1
    _assert_selected_model(session, items)
    assert items[0].payload["subject_name"] == "张三"
    with pytest.raises(KGError) as exc_info:
        apply_suggestion(session, items[0].id)
    assert exc_info.value.code is ErrorCode.SUGGESTION_NOT_APPLICABLE
    # payload 结构可序列化
    dumped = json.dumps(items[0].payload, ensure_ascii=False)
    assert "张三" in dumped


def test_unpublished_resource_kind_filter(session: Session) -> None:
    res = _entity(session, "Assoc", published=False)
    assert res.kind is ResourceKind.ENTITY
    assert res.status is ResourceStatus.DRAFT


def _document_candidate(evidence: object, predicate: str = "") -> dict:
    return {
        "subject_type": "Person",
        "subject_name": "Ada",
        "predicate": predicate,
        "object_type": "Person",
        "object_name": "Grace",
        "evidence": evidence,
    }


def test_document_facts_rejects_unknown_relation_in_empty_catalog(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _entity(session, "Person")
    stub_chat_json(
        session,
        monkeypatch,
        lambda system, user: [_document_candidate("Ada knows Grace", "Invented")],
    )
    assert extract_document_facts(session, _onto_id(session), "Ada knows Grace.") == []
    assert list_suggestions(session, kind="DOCUMENT_FACTS") == []


@pytest.mark.parametrize("evidence", ["", "  ", "Invented quote", None, 17])
def test_document_facts_rejects_evidence_not_in_source(
    session: Session, monkeypatch: pytest.MonkeyPatch, evidence: object
) -> None:
    _entity(session, "Person")
    stub_chat_json(
        session, monkeypatch, lambda system, user: [_document_candidate(evidence)]
    )
    assert extract_document_facts(session, _onto_id(session), "Ada knows Grace.") == []
    assert list_suggestions(session, kind="DOCUMENT_FACTS") == []


def test_document_facts_checks_complete_quote_before_storage_truncation(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _entity(session, "Person")
    prefix = "a" * 500
    stub_chat_json(
        session,
        monkeypatch,
        lambda system, user: [_document_candidate(prefix + " invented")],
    )
    assert (
        extract_document_facts(session, _onto_id(session), prefix + " original") == []
    )
    assert list_suggestions(session, kind="DOCUMENT_FACTS") == []


def test_document_facts_checks_only_text_actually_sent_to_model(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _entity(session, "Person")
    stub_chat_json(
        session, monkeypatch, lambda system, user: [_document_candidate("outside")]
    )
    text = "a" * 20000 + "outside"
    assert extract_document_facts(session, _onto_id(session), text) == []
    assert list_suggestions(session, kind="DOCUMENT_FACTS") == []


def _mapping_fixture(session: Session, tmp_path):

    source_path = tmp_path / "mapping-source.sqlite"
    source = create_engine(f"sqlite:///{source_path}")
    with source.begin() as connection:
        connection.execute(text("CREATE TABLE first_table (id INTEGER, name TEXT)"))
        connection.execute(text("CREATE TABLE second_table (id INTEGER, name TEXT)"))
        connection.execute(text("INSERT INTO first_table VALUES (1, 'First')"))
        connection.execute(text("INSERT INTO second_table VALUES (2, 'Second')"))
    source.dispose()
    datasource = create_datasource(
        session,
        DatasourceCreate(
            name="AI Mapping Source",
            kind="sqlite",
            params={"database": str(source_path)},
        ),
    )
    session.commit()
    capture_metadata(session, datasource.id)
    entity = _entity(session, "Suggestible", with_name_property=True)
    mapping = create_mapping(
        session, MappingCreate(name="AI Mapping", ontology_id=_onto_id(session))
    )
    save_draft(session, mapping.id, MappingRevisionCreate(), if_match=0)
    session.commit()
    return datasource, mapping, entity


def test_mapping_suggestion_rejects_invalid_model_output(
    session: Session, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    datasource, mapping, _ = _mapping_fixture(session, tmp_path)
    stub_chat_json(
        session,
        monkeypatch,
        lambda system, user: [
            {
                "table": "first_table",
                "entity_type": "Suggestible",
                "key_fields": ["missing"],
                "field_maps": [{"target_attr": "missing", "source_field": "missing"}],
            }
        ],
    )
    assert suggest_mapping(session, mapping.id, datasource.id) == []
    assert list_suggestions(session, kind="MAPPING_SUGGEST") == []


def test_mapping_suggestions_reject_old_and_drifted_contexts(
    session: Session, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    datasource, mapping, _ = _mapping_fixture(session, tmp_path)
    stub_chat_json(
        session,
        monkeypatch,
        lambda system, user: [
            {
                "table": "first_table",
                "entity_type": "Suggestible",
                "key_fields": ["id"],
                "field_maps": [{"target_attr": "name", "source_field": "name"}],
            }
        ],
    )
    old = AiSuggestion(
        kind="MAPPING_SUGGEST",
        target_id=mapping.id,
        title="Old suggestion",
        payload={"entity_type": "Suggestible", "table": "first_table"},
    )
    session.add(old)
    session.flush()
    with pytest.raises(KGError) as missing:
        apply_suggestion(session, old.id)
    assert missing.value.params["reason"] == "context_missing_regenerate"

    suggestion = suggest_mapping(session, mapping.id, datasource.id)[0]
    capture_metadata(session, datasource.id)
    session.commit()
    with pytest.raises(KGError) as changed:
        apply_suggestion(session, suggestion.id)
    assert changed.value.params["reason"] == "context_changed_regenerate"


def test_same_batch_mapping_suggestions_apply_sequentially(
    session: Session, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    datasource, mapping, _ = _mapping_fixture(session, tmp_path)
    stub_chat_json(
        session,
        monkeypatch,
        lambda system, user: [
            {
                "table": table,
                "schema": "main",
                "entity_type": "Suggestible",
                "key_fields": ["id"],
                "field_maps": [{"target_attr": "name", "source_field": "name"}],
            }
            for table in ("first_table", "second_table")
        ],
    )
    suggestions = suggest_mapping(session, mapping.id, datasource.id)
    assert len(suggestions) == 2
    _assert_selected_model(session, suggestions)
    apply_suggestion(session, suggestions[0].id)
    apply_suggestion(session, suggestions[1].id)
    draft = get_draft_revision(session, mapping.id)
    assert draft is not None
    assert {entry["table"] for entry in draft.entity_maps} == {
        "first_table",
        "second_table",
    }


@pytest.mark.parametrize("inherited", [False, True])
def test_published_multi_property_suggestions_apply_without_false_drift(
    session: Session, tmp_path, monkeypatch: pytest.MonkeyPatch, inherited: bool
) -> None:
    datasource, mapping, entity = _mapping_fixture(session, tmp_path)
    if inherited:
        parent = _entity(session, "SuggestParent")
        parent.label_i18n = {"zh-CN": "建议父类", "en-US": "SuggestParent"}
        set_data_props(
            session, parent, [DataTypePropCreate(name="zeta", datatype="string")]
        )
        publish_resource(session, parent)
        session.add(ResourceParent(child_id=entity.id, parent_id=parent.id))
        props = [DataTypePropCreate(name="alpha", datatype="string")]
    else:
        props = [
            DataTypePropCreate(name="zeta", datatype="string"),
            DataTypePropCreate(name="alpha", datatype="string"),
        ]
    set_data_props(session, entity, props)
    entity.label_i18n = {"zh-CN": "建议类型", "en-US": "Suggestible"}
    publish_resource(session, entity)
    ontology = session.get(Ontology, _onto_id(session))
    assert ontology is not None
    publish_ontology(session, ontology)
    session.commit()
    stub_chat_json(
        session,
        monkeypatch,
        lambda system, user: [
            {
                "table": "first_table",
                "entity_type": "Suggestible",
                "key_fields": ["id"],
                "field_maps": [{"target_attr": "alpha", "source_field": "name"}],
            }
        ],
    )
    suggestion = suggest_mapping(session, mapping.id, datasource.id)[0]
    assert apply_suggestion(session, suggestion.id).status == "APPLIED"
    draft = get_draft_revision(session, mapping.id)
    assert draft is not None
    assert draft.entity_maps[0]["field_maps"][0]["target_attr"] == "alpha"


def test_same_table_in_two_schemas_can_be_applied_sequentially(
    session: Session, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    datasource, mapping, _ = _mapping_fixture(session, tmp_path)
    snapshot = get_latest_snapshot(session, datasource.id)
    assert snapshot is not None
    snapshot.catalog = {
        "schemas": [
            {
                "schema": schema,
                "tables": [
                    {
                        "name": "first_table",
                        "columns": [{"name": "id"}, {"name": "name"}],
                    }
                ],
            }
            for schema in ("main", "other")
        ]
    }
    session.commit()
    stub_chat_json(
        session,
        monkeypatch,
        lambda system, user: [
            {
                "table": "first_table",
                "schema": schema,
                "entity_type": "Suggestible",
                "key_fields": ["id"],
                "field_maps": [{"target_attr": "name", "source_field": "name"}],
            }
            for schema in ("main", "other")
        ],
    )
    suggestions = suggest_mapping(session, mapping.id, datasource.id)
    assert len(suggestions) == 2
    for suggestion in suggestions:
        apply_suggestion(session, suggestion.id)
        session.commit()
    draft = get_draft_revision(session, mapping.id)
    assert draft is not None
    assert {entry["schema"] for entry in draft.entity_maps} == {"main", "other"}
