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
from app.core import llm
from app.core.db import Base
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.ai_suggestion_service import (
    apply_suggestion,
    discard_suggestion,
    extract_document_facts,
    list_suggestions,
    suggest_ontology_completion,
)
from app.domain.status_service import publish_resource
from app.domain.type_service import create_entity_type
from app.models.account import User
from app.models.domain import Ontology
from app.models.enums import ResourceKind, ResourceStatus, UserRole
from app.schemas.type import EntityTypeCreate
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


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


def _entity(session: Session, name: str, published: bool = False):
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
    with pytest.raises(KGError) as exc_info:
        suggest_ontology_completion(session, onto.id)
    assert exc_info.value.code is ErrorCode.LLM_NOT_CONFIGURED


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
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "chat_json", lambda system, user: payloads)

    items = suggest_ontology_completion(session, _onto_id(session))
    assert len(items) == 1
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
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "chat_json", lambda system, user: payloads)
    items = suggest_ontology_completion(session, _onto_id(session))
    assert len(items) == 1


def test_cannot_apply_to_published_resource(session: Session, monkeypatch) -> None:
    res = _entity(session, "Enterprise", published=True)
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(
        llm,
        "chat_json",
        lambda system, user: [
            {"resource_id": res.id, "label_zh": "企业", "explanation": ""}
        ],
    )
    items = suggest_ontology_completion(session, _onto_id(session))
    with pytest.raises(KGError) as exc_info:
        apply_suggestion(session, items[0].id)
    assert exc_info.value.code is ErrorCode.SUGGESTION_NOT_APPLICABLE


def test_discard_marks_and_rejects_repeat(session: Session, monkeypatch) -> None:
    res = _entity(session, "Person")
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(
        llm, "chat_json", lambda system, user: [
            {"resource_id": res.id, "label_zh": "人员", "explanation": ""}
        ]
    )
    items = suggest_ontology_completion(session, _onto_id(session))
    discarded = discard_suggestion(session, items[0].id)
    assert discarded.status == "DISCARDED"
    with pytest.raises(KGError):
        discard_suggestion(session, items[0].id)
    pending = [item for item in list_suggestions(session, status="PENDING")]
    assert pending == []


def test_document_facts_review_only(session: Session, monkeypatch) -> None:
    _entity(session, "Person")
    _entity(session, "Enterprise")
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(
        llm,
        "chat_json",
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
    assert items[0].payload["subject_name"] == "张三"
    with pytest.raises(KGError) as exc_info:
        apply_suggestion(session, items[0].id)
    assert exc_info.value.code is ErrorCode.SUGGESTION_NOT_APPLICABLE
    assert "张三" in json.dumps(items[0].payload, ensure_ascii=False)  # payload 可序列化


def test_unpublished_resource_kind_filter(session: Session) -> None:
    res = _entity(session, "Assoc", published=False)
    assert res.kind is ResourceKind.ENTITY
    assert res.status is ResourceStatus.DRAFT
