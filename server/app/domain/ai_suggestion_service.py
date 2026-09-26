"""AI 建议服务（第三批：V-DS-05 设计器补全 / V-EX-07 文档抽取与 AI 映射）。

三类建议，全部走同一审阅流程：
- ONTOLOGY_COMPLETION：为草稿类型建议缺失的双语标签/定义
- MAPPING_SUGGEST：按源表结构与本体类型建议字段映射（应用到映射草稿）
- DOCUMENT_FACTS：从粘贴文本抽取候选实体/关系事实（仅审阅，不落库）

可解释性：每条建议带 explanation；确认：应用接口逐条执行，
应用动作只写草稿资产（已发布资源拒绝），绝不静默改写。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import llm
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain import ontology_snapshot
from app.domain.mapping_service import get_draft_revision, get_mapping, save_draft
from app.domain.metadata_service import get_latest_snapshot
from app.models.domain import Ontology, OntologyResourceRef
from app.models.enums import ResourceKind, ResourceStatus
from app.models.governance import AiSuggestion
from app.models.resource import ModelResource
from app.schemas.mapping import (
    EntityMapCreate,
    FieldMap,
    MappingRevisionCreate,
    RelEndpointCandidate,
    RelEndpointSpec,
    RelMapCreate,
    RelMode,
)

SUGGESTION_KINDS = ("ONTOLOGY_COMPLETION", "MAPPING_SUGGEST", "DOCUMENT_FACTS")
_MAX_TEXT = 20000


def _require_llm() -> None:
    if not llm.is_configured():
        raise KGError(
            ErrorCode.LLM_NOT_CONFIGURED, {"reason": "llm_endpoints_not_configured"}
        )


def list_suggestions(
    session: Session, kind: str | None = None, status: str | None = None
) -> list[AiSuggestion]:
    stmt = select(AiSuggestion).order_by(AiSuggestion.id.desc())
    if kind:
        stmt = stmt.where(AiSuggestion.kind == kind)
    if status:
        stmt = stmt.where(AiSuggestion.status == status)
    return list(session.scalars(stmt))


def get_suggestion(session: Session, suggestion_id: int) -> AiSuggestion:
    item = session.get(AiSuggestion, suggestion_id)
    if item is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"suggestion_id": suggestion_id})
    return item


def _persist(
    session: Session, kind: str, target_id: int, items: list[dict]
) -> list[AiSuggestion]:
    rows: list[AiSuggestion] = []
    for item in items:
        payload = {
            key: value
            for key, value in item.items()
            if key not in {"title", "explanation"}
        }
        row = AiSuggestion(
            kind=kind,
            target_id=target_id,
            status="PENDING",
            title=str(item.get("title", ""))[:256] or "(untitled)",
            payload=payload,
            explanation=str(item.get("explanation", "")),
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


# ---------- ONTOLOGY_COMPLETION ----------

_COMPLETION_SYSTEM = (
    "你是知识建模助手。根据缺失的双语标签与定义，为每个资源输出一个 JSON 数组，"
    '数组元素形如 {"resource_id": 整数, "label_zh": str, "label_en": str, '
    '"definition_zh": str, "definition_en": str, "explanation": str}。'
    "只输出 JSON，不要输出其他文字。"
)


def suggest_ontology_completion(
    session: Session, ontology_id: int
) -> list[AiSuggestion]:
    onto = session.get(Ontology, ontology_id)
    if onto is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"ontology_id": ontology_id})
    _require_llm()
    refs = list(
        session.scalars(
            select(OntologyResourceRef).where(
                OntologyResourceRef.ontology_id == ontology_id
            )
        )
    )
    context: list[dict] = []
    for ref in refs:
        res = session.get(ModelResource, ref.resource_id)
        if res is None or res.kind not in (ResourceKind.ENTITY, ResourceKind.ASSOC):
            continue
        missing_label = not (res.label_i18n or {}).get("zh-CN")
        missing_def = not (res.definition_i18n or {}).get("zh-CN")
        if not (missing_label or missing_def):
            continue
        context.append(
            {"resource_id": res.id, "name": res.name, "kind": res.kind.value}
        )
    if not context:
        return []
    raw = llm.chat_json(
        _COMPLETION_SYSTEM,
        json.dumps(context, ensure_ascii=False)[:_MAX_TEXT],
    )
    items: list[dict] = []
    valid_ids = {entry["resource_id"] for entry in context}
    for item in raw:
        try:
            resource_id = int(item.get("resource_id", 0))
            if resource_id not in valid_ids:
                continue
            label_zh = str(item["label_zh"]).strip()
            title = label_zh or str(item.get("label_en", ""))
            if not title:
                continue
            items.append(
                {
                    "resource_id": resource_id,
                    "label_zh": label_zh,
                    "label_en": str(item.get("label_en", "")).strip(),
                    "definition_zh": str(item.get("definition_zh", "")).strip(),
                    "definition_en": str(item.get("definition_en", "")).strip(),
                    "title": title,
                    "explanation": str(item.get("explanation", "")),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return _persist(session, "ONTOLOGY_COMPLETION", ontology_id, items)


# ---------- MAPPING_SUGGEST ----------

_MAPPING_SYSTEM = (
    "你是数据集成助手。根据源表结构、样例行与本体类型，为每张建议的映射输出一个 JSON "
    '数组元素：{"table": str, "entity_type": str, "key_fields": [str], '
    '"field_maps": [{"target_attr": str, "source_field": str}], "explanation": str}。'
    "target_attr 必须来自本体类型的数据属性；source_field 必须来自源表列。"
    "只输出 JSON，不要输出其他文字。"
)


def suggest_mapping(
    session: Session, mapping_id: int, datasource_id: int
) -> list[AiSuggestion]:
    mapping = get_mapping(session, mapping_id)
    _require_llm()
    # 本体类型上下文（草稿或冻结快照）
    onto = session.get(Ontology, mapping.ontology_id)
    if onto is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND, {"ontology_id": mapping.ontology_id}
        )
    types: list[dict] = []
    if onto.status == ResourceStatus.PUBLISHED and onto.current_revision > 0:
        resources = list(
            ontology_snapshot.load_ontology_snapshot(
                session, onto.id, onto.current_revision
            ).values()
        )
        for res in resources:
            if res.kind in (ResourceKind.ENTITY, ResourceKind.ASSOC):
                types.append(
                    {
                        "name": res.name,
                        "props": [prop.name for prop in res.datatype_props],
                    }
                )
    else:
        refs = list(
            session.scalars(
                select(OntologyResourceRef).where(
                    OntologyResourceRef.ontology_id == onto.id
                )
            )
        )
        for ref in refs:
            resource = session.get(ModelResource, ref.resource_id)
            if resource is None or resource.kind not in (
                ResourceKind.ENTITY,
                ResourceKind.ASSOC,
            ):
                continue
            types.append({"name": resource.name, "props": []})
    if not types:
        return []

    snap = get_latest_snapshot(session, datasource_id)
    if snap is None:
        raise KGError(
            ErrorCode.INVALID_REQUEST,
            {"datasource_id": datasource_id, "reason": "no_metadata_snapshot"},
        )
    tables: list[dict] = []
    for schema in snap.catalog.get("schemas", [])[:5]:
        for table in schema.get("tables", [])[:10]:
            tables.append(
                {
                    "schema": schema.get("schema", "main"),
                    "name": table["name"],
                    "columns": [col["name"] for col in table.get("columns", [])][:30],
                }
            )
    raw = llm.chat_json(
        _MAPPING_SYSTEM,
        json.dumps(
            {"ontology_types": types, "tables": tables},
            ensure_ascii=False,
        )[:_MAX_TEXT],
    )
    valid_types = {entry["name"] for entry in types}
    table_columns = {entry["name"]: set(entry["columns"]) for entry in tables}
    items: list[dict] = []
    for item in raw:
        table = str(item.get("table", ""))
        entity_type = str(item.get("entity_type", ""))
        columns = table_columns.get(table)
        if columns is None or entity_type not in valid_types:
            continue
        field_maps = []
        for field in item.get("field_maps", []) or []:
            target = str(field.get("target_attr", ""))
            source = str(field.get("source_field", ""))
            if target and source and source in columns:
                field_maps.append({"target_attr": target, "source_field": source})
        if not field_maps:
            continue
        items.append(
            {
                "table": table,
                "entity_type": entity_type,
                "key_fields": [str(k) for k in (item.get("key_fields") or [])[:5]],
                "field_maps": field_maps,
                "title": f"{table} → {entity_type}",
                "explanation": str(item.get("explanation", "")),
            }
        )
    return _persist(session, "MAPPING_SUGGEST", mapping_id, items)


# ---------- DOCUMENT_FACTS ----------

_DOCUMENT_SYSTEM = (
    "你是信息抽取助手。根据本体类型从文本中抽取候选实体与关系事实，"
    '输出 JSON 数组，元素形如 {"subject_type": str, "subject_name": str, '
    '"predicate": str, "object_type": str, "object_name": str, '
    '"evidence": str, "explanation": str}。类型必须来自给出的本体；'
    "证据必须是原文片段。只输出 JSON，不要输出其他文字。"
)


def extract_document_facts(
    session: Session, ontology_id: int, text: str
) -> list[AiSuggestion]:
    onto = session.get(Ontology, ontology_id)
    if onto is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"ontology_id": ontology_id})
    _require_llm()
    if not text.strip():
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "empty_text"})
    refs = list(
        session.scalars(
            select(OntologyResourceRef).where(
                OntologyResourceRef.ontology_id == ontology_id
            )
        )
    )
    names = sorted(
        {
            res.name
            for res in (session.get(ModelResource, ref.resource_id) for ref in refs)
            if res is not None and res.kind in (ResourceKind.ENTITY, ResourceKind.ASSOC)
        }
    )
    relations = sorted(
        {
            res.name
            for res in (session.get(ModelResource, ref.resource_id) for ref in refs)
            if res is not None and res.kind == ResourceKind.OBJECT_PROP
        }
    )
    raw = llm.chat_json(
        _DOCUMENT_SYSTEM,
        json.dumps(
            {
                "entity_types": names,
                "relations": relations,
                "text": text.strip()[:_MAX_TEXT],
            },
            ensure_ascii=False,
        ),
    )
    type_set = set(names)
    relation_set = set(relations)
    items: list[dict] = []
    for item in raw:
        subject_type = str(item.get("subject_type", ""))
        object_type = str(item.get("object_type", ""))
        predicate = str(item.get("predicate", ""))
        if subject_type not in type_set or object_type not in type_set:
            continue
        if relation_set and predicate not in relation_set:
            continue
        subject_name = str(item.get("subject_name", "")).strip()
        object_name = str(item.get("object_name", "")).strip()
        if not subject_name or not object_name:
            continue
        items.append(
            {
                "subject_type": subject_type,
                "subject_name": subject_name,
                "predicate": predicate,
                "object_type": object_type,
                "object_name": object_name,
                "evidence": str(item.get("evidence", ""))[:500],
                "title": f"{subject_name} —{predicate}→ {object_name}",
                "explanation": str(item.get("explanation", "")),
            }
        )
    return _persist(session, "DOCUMENT_FACTS", ontology_id, items)


# ---------- 审阅：应用 / 忽略 ----------


def apply_suggestion(session: Session, suggestion_id: int) -> AiSuggestion:
    """人工确认后落库。只写草稿资产；不适用/已处理如实拒绝。"""
    item = get_suggestion(session, suggestion_id)
    if item.status != "PENDING":
        raise KGError(
            ErrorCode.SUGGESTION_NOT_APPLICABLE,
            {"suggestion_id": item.id, "status": item.status},
        )
    if item.kind == "ONTOLOGY_COMPLETION":
        _apply_completion(session, item)
    elif item.kind == "MAPPING_SUGGEST":
        _apply_mapping_suggestion(session, item)
    else:
        raise KGError(
            ErrorCode.SUGGESTION_NOT_APPLICABLE,
            {"suggestion_id": item.id, "kind": item.kind, "reason": "review_only"},
        )
    item.status = "APPLIED"
    item.resolved_at = datetime.now(UTC)
    session.flush()
    return item


def discard_suggestion(session: Session, suggestion_id: int) -> AiSuggestion:
    item = get_suggestion(session, suggestion_id)
    if item.status != "PENDING":
        raise KGError(
            ErrorCode.SUGGESTION_NOT_APPLICABLE,
            {"suggestion_id": item.id, "status": item.status},
        )
    item.status = "DISCARDED"
    item.resolved_at = datetime.now(UTC)
    session.flush()
    return item


def _apply_completion(session: Session, item: AiSuggestion) -> None:
    payload = item.payload
    res = session.get(ModelResource, int(payload["resource_id"]))
    if res is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND, {"resource_id": payload["resource_id"]}
        )
    if res.status == ResourceStatus.PUBLISHED:
        raise KGError(
            ErrorCode.SUGGESTION_NOT_APPLICABLE,
            {"resource": res.name, "reason": "resource_published"},
        )
    labels = dict(res.label_i18n or {})
    definitions = dict(res.definition_i18n or {})
    if payload.get("label_zh"):
        labels["zh-CN"] = str(payload["label_zh"])
    if payload.get("label_en"):
        labels["en-US"] = str(payload["label_en"])
    if payload.get("definition_zh"):
        definitions["zh-CN"] = str(payload["definition_zh"])
    if payload.get("definition_en"):
        definitions["en-US"] = str(payload["definition_en"])
    res.label_i18n = labels
    res.definition_i18n = definitions
    session.flush()


def _apply_mapping_suggestion(session: Session, item: AiSuggestion) -> None:
    mapping = get_mapping(session, item.target_id)
    if mapping.status == ResourceStatus.PUBLISHED:
        raise KGError(
            ErrorCode.SUGGESTION_NOT_APPLICABLE,
            {"mapping": mapping.name, "reason": "mapping_published_immutable"},
        )
    payload = item.payload
    table = str(payload["table"])
    entity_type = str(payload["entity_type"])
    field_maps = [FieldMap(**field) for field in payload.get("field_maps", [])]
    new_entity = EntityMapCreate(
        entity_type=entity_type,
        table=table,
        field_maps=field_maps,
        key_fields=[str(k) for k in payload.get("key_fields", [])],
    )
    draft = get_draft_revision(session, mapping.id)
    if draft is None:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"mapping_id": mapping.id, "reason": "no_draft"},
        )
    entity_maps = [_entity_from_dict(entry) for entry in draft.entity_maps]
    if any(
        entry.entity_type == entity_type and entry.table == table
        for entry in entity_maps
    ):
        raise KGError(
            ErrorCode.SUGGESTION_NOT_APPLICABLE,
            {
                "reason": "duplicate_entity_map",
                "entity_type": entity_type,
                "table": table,
            },
        )
    entity_maps.append(new_entity)
    rel_maps = [_rel_from_dict(entry) for entry in draft.rel_maps]
    save_draft(
        session,
        mapping.id,
        MappingRevisionCreate(entity_maps=entity_maps, rel_maps=rel_maps),
        if_match=mapping.current_revision,
        if_edit_match=mapping.edit_revision,
    )


def _entity_from_dict(entry: dict) -> EntityMapCreate:
    return EntityMapCreate(
        entity_type=str(entry.get("entity_type", "")),
        table=str(entry.get("table", "")),
        schema=str(entry.get("schema", "main")),
        field_maps=[
            FieldMap(
                target_attr=str(field.get("target_attr", "")),
                source_field=str(field.get("source_field", "")),
            )
            for field in entry.get("field_maps", [])
        ],
        key_fields=[str(k) for k in entry.get("key_fields", [])],
        match_keys=[str(k) for k in entry.get("match_keys", [])],
        incremental_field=entry.get("incremental_field"),
    )


def _rel_from_dict(entry: dict) -> RelMapCreate:
    def endpoint(value: dict | None) -> RelEndpointSpec | None:
        if not value:
            return None
        return RelEndpointSpec(
            field=str(value.get("field", "")),
            ref_table=str(value.get("ref_table", "")),
            ref_field=str(value.get("ref_field", "")),
            candidates=[
                RelEndpointCandidate(
                    field=str(cand.get("field", "")),
                    ref_table=str(cand.get("ref_table", "")),
                    when=cand.get("when"),
                    ref_entity_type=cand.get("ref_entity_type"),
                )
                for cand in value.get("candidates", [])
            ],
            type_field=value.get("type_field"),
            via=value.get("via"),
        )

    return RelMapCreate(
        relation_type=str(entry.get("relation_type", "")),
        mode=RelMode(entry.get("mode", "JUNCTION")),
        table=str(entry.get("table", "")),
        schema=str(entry.get("schema", "main")),
        fk_field=entry.get("fk_field"),
        source=endpoint(entry.get("source")),
        target=endpoint(entry.get("target")),
        attributes=list(entry.get("attributes", [])),
    )
