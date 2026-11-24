"""AI 建议服务（第三批：V-DS-05 设计器补全 / V-EX-07 文档抽取与 AI 映射）。

三类建议，全部走同一审阅流程：
- ONTOLOGY_COMPLETION：为草稿类型建议缺失的双语标签/定义
- MAPPING_SUGGEST：按源表结构与本体类型建议字段映射（应用到映射草稿）
- DOCUMENT_FACTS：从粘贴文本抽取候选实体/关系事实（仅审阅，不落库）

可解释性：每条建议带 explanation；确认：应用接口逐条执行，
应用动作只写草稿资产（已发布资源拒绝），绝不静默改写。
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import llm
from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain import ontology_snapshot
from app.domain.ai_model_service import ResolvedModel, resolve_default
from app.domain.asset_audit_service import record_asset_audit
from app.domain.mapping_service import get_draft_revision, get_mapping, save_draft
from app.domain.metadata_service import get_latest_snapshot, get_snapshot
from app.domain.status_service import lock_resource_edit
from app.models.asset_audit import AssetAuditAction, AssetType
from app.models.domain import Ontology, OntologyResourceRef, OntologyRevision
from app.models.enums import AuditResult, ResourceKind, ResourceStatus
from app.models.governance import AiSuggestion
from app.models.resource import (
    DatatypePropDetail,
    ModelResource,
    ResourceParent,
    ResourceRef,
)
from app.schemas.mapping import (
    EntityMapCreate,
    FieldMap,
    MappingRevisionCreate,
    RelMapCreate,
)

SUGGESTION_KINDS = ("ONTOLOGY_COMPLETION", "MAPPING_SUGGEST", "DOCUMENT_FACTS")
_MAX_TEXT = 20000


def _require_llm(session: Session) -> ResolvedModel:
    model = resolve_default(session, "CHAT")
    if model is None:
        raise KGError(
            ErrorCode.LLM_NOT_CONFIGURED,
            {"reason": "default_chat_model_not_configured"},
        )
    return model


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
    session: Session,
    kind: str,
    target_id: int,
    items: list[dict],
    *,
    model: ResolvedModel,
) -> list[AiSuggestion]:
    rows: list[AiSuggestion] = []
    for item in items:
        payload = {
            key: value
            for key, value in item.items()
            if key not in {"title", "explanation"}
        }
        payload["_model"] = {
            "config_id": model.config_id,
            "config_revision": model.config_revision,
            "default_revision": model.default_revision,
            "model": model.endpoint.model,
            "model_version": model.model_version,
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


def _fingerprint(context: dict) -> str:
    return hashlib.sha256(
        json.dumps(context, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _completion_resource_context(resource: ModelResource) -> dict:
    return {
        "id": resource.id,
        "name": resource.name,
        "iri": resource.iri,
        "namespace_id": resource.namespace_id,
        "kind": resource.kind.value,
        "status": resource.status.value,
        "current_revision": resource.current_revision,
        "edit_revision": resource.edit_revision,
        "label_i18n": deepcopy(resource.label_i18n),
        "definition_i18n": deepcopy(resource.definition_i18n),
    }


def _completion_ontology_context(session: Session, onto: Ontology) -> dict:
    return {
        "id": onto.id,
        "name": onto.name,
        "iri": onto.iri,
        "status": onto.status.value,
        "current_revision": onto.current_revision,
        "edit_revision": onto.edit_revision,
        "template_id": onto.template_id,
        "label_i18n": deepcopy(onto.label_i18n),
        "definition_i18n": deepcopy(onto.definition_i18n),
        "members": [
            {"resource_id": resource_id, "pinned_revision": revision}
            for resource_id, revision in session.execute(
                select(
                    OntologyResourceRef.resource_id,
                    OntologyResourceRef.pinned_revision,
                )
                .where(OntologyResourceRef.ontology_id == onto.id)
                .order_by(OntologyResourceRef.resource_id)
            )
        ],
    }


def _completion_changed(ontology_id: int) -> KGError:
    return KGError(
        ErrorCode.SUGGESTION_NOT_APPLICABLE,
        {"ontology_id": ontology_id, "reason": "context_changed_regenerate"},
    )


def suggest_ontology_completion(
    session: Session, ontology_id: int
) -> list[AiSuggestion]:
    onto = session.get(Ontology, ontology_id, populate_existing=True)
    if onto is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"ontology_id": ontology_id})
    model = _require_llm(session)
    ontology_context = _completion_ontology_context(session, onto)
    context: list[dict] = []
    baselines: dict[int, dict] = {}
    for member in ontology_context["members"]:
        res = session.get(ModelResource, member["resource_id"], populate_existing=True)
        if (
            res is None
            or res.kind not in (ResourceKind.ENTITY, ResourceKind.ASSOC)
            or res.status != ResourceStatus.DRAFT
        ):
            continue
        missing_label = not (res.label_i18n or {}).get("zh-CN")
        missing_def = not (res.definition_i18n or {}).get("zh-CN")
        if not (missing_label or missing_def):
            continue
        entry = {"resource_id": res.id, "name": res.name, "kind": res.kind.value}
        # Only authorize IDs actually sent in a complete JSON array.
        if len(json.dumps([*context, entry], ensure_ascii=False)) > _MAX_TEXT:
            break
        context.append(entry)
        baselines[res.id] = {
            "version": 1,
            "ontology": ontology_context,
            "resource": _completion_resource_context(res),
        }
    if not context:
        return []
    raw = llm.chat_json(
        _COMPLETION_SYSTEM,
        json.dumps(context, ensure_ascii=False),
        endpoint=model.endpoint,
    )
    # Re-read authoritative rows after the slow model call, including cached ORM rows.
    onto = session.get(Ontology, ontology_id, populate_existing=True)
    if onto is None or _completion_ontology_context(session, onto) != ontology_context:
        raise _completion_changed(ontology_id)
    for resource_id, baseline in baselines.items():
        res = session.get(ModelResource, resource_id, populate_existing=True)
        if res is None or _completion_resource_context(res) != baseline["resource"]:
            raise _completion_changed(ontology_id)
    items: list[dict] = []
    for item in raw:
        try:
            model_id = item.get("resource_id")
            if type(model_id) is not int and not (
                isinstance(model_id, str)
                and model_id.isascii()
                and model_id.isdecimal()
            ):
                continue
            resource_id = int(model_id)
            if resource_id not in baselines:
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
                    "_context": baselines[resource_id],
                    "_context_id": _fingerprint(baselines[resource_id]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return _persist(session, "ONTOLOGY_COMPLETION", ontology_id, items, model=model)


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
    model = _require_llm(session)
    # 本体类型上下文（草稿或冻结快照）
    onto = session.get(Ontology, mapping.ontology_id)
    if onto is None:
        raise KGError(
            ErrorCode.RESOURCE_NOT_FOUND, {"ontology_id": mapping.ontology_id}
        )
    types: list[dict] = []
    ontology_context: dict
    if onto.status == ResourceStatus.PUBLISHED and onto.current_revision > 0:
        snapshots = ontology_snapshot.load_ontology_snapshot(
            session, onto.id, onto.current_revision
        )
        resources = list(snapshots.values())
        for res in resources:
            if res.kind in (ResourceKind.ENTITY, ResourceKind.ASSOC):
                types.append(
                    {
                        "id": res.id,
                        "name": res.name,
                        "parents": sorted(res.parent_ids),
                        "props": sorted(
                            prop.name
                            for prop in ontology_snapshot.effective_datatype_props(
                                snapshots, res.id
                            )
                        ),
                    }
                )
        onto_revision = session.scalar(
            select(OntologyRevision).where(
                OntologyRevision.ontology_id == onto.id,
                OntologyRevision.revision == onto.current_revision,
            )
        )
        ontology_context = {
            "mode": "PUBLISHED",
            "revision": onto.current_revision,
            "resource_versions": onto_revision.resource_versions
            if onto_revision
            else {},
            "types": sorted(types, key=lambda entry: entry["id"]),
        }
    else:
        refs = list(
            session.scalars(
                select(OntologyResourceRef).where(
                    OntologyResourceRef.ontology_id == onto.id
                )
            )
        )
        live_types: dict[int, dict] = {}
        member_pins: dict[str, int] = {}
        for ref in refs:
            resource = session.get(ModelResource, ref.resource_id)
            if resource is None or resource.kind not in (
                ResourceKind.ENTITY,
                ResourceKind.ASSOC,
            ):
                continue
            pin = ref.pinned_revision or resource.current_revision
            if pin > 0:
                snapshot = ontology_snapshot.load_resource_snapshot(
                    session, resource.id, pin
                )
                live_types[resource.id] = {
                    "id": resource.id,
                    "name": snapshot.name,
                    "props": [prop.name for prop in snapshot.datatype_props],
                    "parents": snapshot.parent_ids,
                }
                member_pins[str(resource.id)] = pin
            else:
                prop_names = list(
                    session.scalars(
                        select(DatatypePropDetail.prop_name)
                        .join(
                            ResourceRef,
                            ResourceRef.target_id == DatatypePropDetail.resource_id,
                        )
                        .where(
                            ResourceRef.source_id == resource.id,
                            ResourceRef.role.in_(["data_prop", "assoc_attribute"]),
                        )
                    )
                )
                parents = list(
                    session.scalars(
                        select(ResourceParent.parent_id).where(
                            ResourceParent.child_id == resource.id
                        )
                    )
                )
                live_types[resource.id] = {
                    "id": resource.id,
                    "name": resource.name,
                    "props": prop_names,
                    "parents": parents,
                }
                member_pins[str(resource.id)] = 0
        state: dict[int, int] = {}

        def effective_props(resource_id: int) -> set[str]:
            marker = state.get(resource_id, 0)
            if marker == 1:
                raise KGError(
                    ErrorCode.VALIDATION_VIOLATION,
                    {"resource_id": resource_id, "reason": "inheritance_cycle"},
                )
            entry = live_types.get(resource_id)
            if entry is None:
                raise KGError(
                    ErrorCode.VALIDATION_VIOLATION,
                    {"resource_id": resource_id, "reason": "missing_parent_snapshot"},
                )
            if marker == 2:
                return entry["effective_props"]
            state[resource_id] = 1
            props = set(entry["props"])
            for parent_id in entry["parents"]:
                props.update(effective_props(parent_id))
            state[resource_id] = 2
            entry["effective_props"] = props
            return props

        for resource_id, entry in sorted(live_types.items()):
            types.append(
                {
                    "id": resource_id,
                    "name": entry["name"],
                    "parents": sorted(entry["parents"]),
                    "props": sorted(effective_props(resource_id)),
                }
            )
        ontology_context = {
            "mode": "DRAFT",
            "resource_versions": member_pins,
            "types": sorted(types, key=lambda entry: entry["id"]),
        }
    if not types:
        return []

    snap = get_latest_snapshot(session, datasource_id)
    if snap is None:
        raise KGError(
            ErrorCode.INVALID_REQUEST,
            {"datasource_id": datasource_id, "reason": "no_metadata_snapshot"},
        )
    tables: list[dict] = []
    for schema in snap.catalog.get("schemas", []):
        for table in schema.get("tables", []):
            source_columns = [col["name"] for col in table.get("columns", [])]
            if len(tables) >= 50:
                continue
            tables.append(
                {
                    "schema": schema.get("schema", "main"),
                    "name": table["name"],
                    "columns": source_columns[:100],
                }
            )
    draft = get_draft_revision(session, mapping.id)
    if draft is None:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"mapping_id": mapping.id, "reason": "no_draft"},
        )
    context = {
        "datasource_id": datasource_id,
        "metadata_snapshot_id": snap.id,
        "metadata_revision": snap.revision,
        "ontology": ontology_context,
    }
    context_id = hashlib.sha256(
        json.dumps(context, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    raw = llm.chat_json(
        _MAPPING_SYSTEM,
        json.dumps(
            {"ontology_types": types, "tables": tables},
            ensure_ascii=False,
        )[:_MAX_TEXT],
        endpoint=model.endpoint,
    )
    valid_types = {entry["name"]: set(entry["props"]) for entry in types}
    table_columns = {
        (entry["schema"], entry["name"]): set(entry["columns"]) for entry in tables
    }
    items: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        table = str(item.get("table", ""))
        schema_name = str(item.get("schema", "main"))
        entity_type = str(item.get("entity_type", ""))
        columns = table_columns.get((schema_name, table))
        props = valid_types.get(entity_type)
        if columns is None or props is None:
            continue
        field_maps = []
        raw_field_maps = item.get("field_maps", []) or []
        if not isinstance(raw_field_maps, list):
            continue
        for field in raw_field_maps:
            if not isinstance(field, dict):
                continue
            target = str(field.get("target_attr", ""))
            source = str(field.get("source_field", ""))
            if target in props and source and source in columns:
                field_maps.append({"target_attr": target, "source_field": source})
        if not field_maps:
            continue
        raw_key_fields = item.get("key_fields") or []
        if not isinstance(raw_key_fields, list) or any(
            not isinstance(key, str) or not key.strip() or key not in columns
            for key in raw_key_fields
        ):
            continue
        key_fields = list(raw_key_fields)
        items.append(
            {
                "table": table,
                "schema": schema_name,
                "entity_type": entity_type,
                "key_fields": key_fields[:5],
                "field_maps": field_maps,
                "_context": context,
                "_context_id": context_id,
                "title": f"{table} → {entity_type}",
                "explanation": str(item.get("explanation", "")),
            }
        )
    return _persist(session, "MAPPING_SUGGEST", mapping_id, items, model=model)


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
    model = _require_llm(session)
    if not text.strip():
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "empty_text"})
    source_text = text.strip()[:_MAX_TEXT]
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
                "text": source_text,
            },
            ensure_ascii=False,
        ),
        endpoint=model.endpoint,
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
        if predicate and predicate not in relation_set:
            continue
        subject_name = str(item.get("subject_name", "")).strip()
        object_name = str(item.get("object_name", "")).strip()
        if not subject_name or not object_name:
            continue
        evidence = item.get("evidence")
        if not isinstance(evidence, str):
            continue
        evidence = evidence.strip()
        if not evidence or evidence not in source_text:
            continue
        items.append(
            {
                "subject_type": subject_type,
                "subject_name": subject_name,
                "predicate": predicate,
                "object_type": object_type,
                "object_name": object_name,
                "evidence": evidence[:500],
                "title": f"{subject_name} —{predicate}→ {object_name}",
                "explanation": str(item.get("explanation", "")),
            }
        )
    return _persist(session, "DOCUMENT_FACTS", ontology_id, items, model=model)


# ---------- 审阅：应用 / 忽略 ----------


def _claim_pending(
    session: Session, suggestion_id: int, *, status: str = "PENDING"
) -> AiSuggestion:
    # The conditional write locks the row until the caller commits/rolls back.
    # Keeping PENDING during apply leaves rejected suggestions pending.
    item = session.scalar(
        update(AiSuggestion)
        .where(AiSuggestion.id == suggestion_id, AiSuggestion.status == "PENDING")
        .values(
            status=status,
            resolved_at=datetime.now(UTC)
            if status == "DISCARDED"
            else AiSuggestion.resolved_at,
        )
        .returning(AiSuggestion)
        .execution_options(populate_existing=True)
    )
    if item is None:
        item = session.get(AiSuggestion, suggestion_id, populate_existing=True)
        if item is None:
            raise KGError(
                ErrorCode.RESOURCE_NOT_FOUND, {"suggestion_id": suggestion_id}
            )
        raise KGError(
            ErrorCode.SUGGESTION_NOT_APPLICABLE,
            {"suggestion_id": item.id, "status": item.status},
        )
    return item


def apply_suggestion(
    session: Session,
    suggestion_id: int,
    *,
    actor_id: str | None = None,
    correlation_id: str | None = None,
) -> AiSuggestion:
    """人工确认后落库。只写草稿资产；不适用/已处理如实拒绝。"""
    item = _claim_pending(session, suggestion_id)
    if item.kind == "ONTOLOGY_COMPLETION":
        resource, before = _apply_completion(session, item)
        object_type = (
            AssetType.ENTITY_TYPE
            if resource.kind == ResourceKind.ENTITY
            else AssetType.RELATION_TYPE
        )
        object_id = resource.id
        after: dict[str, int | None] = {
            "current_revision": resource.current_revision,
            "edit_revision": resource.edit_revision,
        }
    elif item.kind == "MAPPING_SUGGEST":
        mapping = get_mapping(session, item.target_id)
        before = {
            "current_revision": mapping.current_revision,
            "edit_revision": mapping.edit_revision,
        }
        _apply_mapping_suggestion(session, item)
        object_type, object_id = AssetType.MAPPING, mapping.id
        after = {
            "current_revision": mapping.current_revision,
            "edit_revision": mapping.edit_revision,
        }
    else:
        raise KGError(
            ErrorCode.SUGGESTION_NOT_APPLICABLE,
            {"suggestion_id": item.id, "kind": item.kind, "reason": "review_only"},
        )
    item.status = "APPLIED"
    item.resolved_at = datetime.now(UTC)
    # HTTP supplies the authenticated actor; standalone domain callers own that context.
    # The audit and the resource/status updates share the caller's transaction.
    if actor_id is not None:
        record_asset_audit(
            session,
            actor_id=actor_id,
            action=AssetAuditAction.EDIT,
            object_type=object_type,
            object_id=object_id,
            version_before=before,
            version_after=after,
            result=AuditResult.OK,
            correlation_id=correlation_id or uuid4().hex,
        )
    session.flush()
    return item


def discard_suggestion(session: Session, suggestion_id: int) -> AiSuggestion:
    return _claim_pending(session, suggestion_id, status="DISCARDED")


def _apply_completion(
    session: Session, item: AiSuggestion
) -> tuple[ModelResource, dict[str, int | None]]:
    payload = item.payload
    context = payload.get("_context")
    if (
        not isinstance(context, dict)
        or context.get("version") != 1
        or not isinstance(context.get("ontology"), dict)
        or not isinstance(context.get("resource"), dict)
        or not isinstance(payload.get("_context_id"), str)
    ):
        raise KGError(
            ErrorCode.SUGGESTION_NOT_APPLICABLE,
            {"suggestion_id": item.id, "reason": "context_missing_regenerate"},
        )
    ontology_context, resource_context = context["ontology"], context["resource"]
    if (
        _fingerprint(context) != payload["_context_id"]
        or ontology_context.get("id") != item.target_id
        or resource_context.get("id") != payload.get("resource_id")
        or type(resource_context.get("id")) is not int
        or any(
            type(baseline.get(key)) is not int
            for baseline in (ontology_context, resource_context)
            for key in ("current_revision", "edit_revision")
        )
    ):
        raise _completion_changed(item.target_id)
    # Serialize against member/pin edits without advancing the ontology token:
    # independent resources from the same generated batch may still apply in sequence.
    onto = session.scalar(
        update(Ontology)
        .where(
            Ontology.id == item.target_id,
            Ontology.status == ontology_context.get("status"),
            Ontology.current_revision == ontology_context["current_revision"],
            Ontology.edit_revision == ontology_context["edit_revision"],
        )
        .values(edit_revision=Ontology.edit_revision)
        .returning(Ontology)
        .execution_options(populate_existing=True)
    )
    if onto is None or _completion_ontology_context(session, onto) != ontology_context:
        raise _completion_changed(item.target_id)
    res = session.get(ModelResource, resource_context["id"], populate_existing=True)
    if (
        res is None
        or res.status != ResourceStatus.DRAFT
        or res.kind not in (ResourceKind.ENTITY, ResourceKind.ASSOC)
        or _completion_resource_context(res) != resource_context
        or not any(
            member["resource_id"] == res.id for member in ontology_context["members"]
        )
    ):
        raise _completion_changed(item.target_id)
    before: dict[str, int | None] = {
        "current_revision": res.current_revision,
        "edit_revision": res.edit_revision,
    }
    res = lock_resource_edit(
        session,
        res,
        resource_context["current_revision"],
        resource_context["edit_revision"],
    )
    # A legacy writer might change content without advancing a token.
    locked_context = _completion_resource_context(res)
    locked_context["edit_revision"] -= 1
    if locked_context != resource_context:
        raise _completion_changed(item.target_id)
    labels = dict(res.label_i18n or {})
    definitions = dict(res.definition_i18n or {})
    for values, fields in (
        (labels, (("zh-CN", "label_zh"), ("en-US", "label_en"))),
        (definitions, (("zh-CN", "definition_zh"), ("en-US", "definition_en"))),
    ):
        for locale, field in fields:
            if not values.get(locale) and payload.get(field):
                values[locale] = str(payload[field])
    res.label_i18n = labels
    res.definition_i18n = definitions
    session.flush()
    return res, before


def _apply_mapping_suggestion(session: Session, item: AiSuggestion) -> None:
    mapping = get_mapping(session, item.target_id)
    if mapping.status == ResourceStatus.PUBLISHED:
        raise KGError(
            ErrorCode.SUGGESTION_NOT_APPLICABLE,
            {"mapping": mapping.name, "reason": "mapping_published_immutable"},
        )
    payload = item.payload
    context = payload.get("_context")
    if (
        not isinstance(context, dict)
        or not isinstance(payload.get("_context_id"), str)
        or not isinstance(context.get("datasource_id"), int)
        or not isinstance(context.get("metadata_snapshot_id"), int)
        or not isinstance(context.get("metadata_revision"), int)
        or not isinstance(context.get("ontology"), dict)
    ):
        raise KGError(
            ErrorCode.SUGGESTION_NOT_APPLICABLE,
            {"suggestion_id": item.id, "reason": "context_missing_regenerate"},
        )
    mapping_context = _mapping_context(
        session, mapping.id, int(context["datasource_id"])
    )
    stable_keys = (
        "datasource_id",
        "metadata_snapshot_id",
        "metadata_revision",
        "ontology",
    )
    if (
        any(mapping_context.get(key) != context.get(key) for key in stable_keys)
        or hashlib.sha256(
            json.dumps(context, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        != payload["_context_id"]
    ):
        raise KGError(
            ErrorCode.SUGGESTION_NOT_APPLICABLE,
            {"suggestion_id": item.id, "reason": "context_changed_regenerate"},
        )
    _validate_mapping_suggestion_sources(session, context, payload)
    table = str(payload["table"])
    entity_type = str(payload["entity_type"])
    field_maps = [FieldMap(**field) for field in payload.get("field_maps", [])]
    new_entity = EntityMapCreate(
        entity_type=entity_type,
        table=table,
        schema=str(payload.get("schema", "main")),
        field_maps=field_maps,
        key_fields=[str(k) for k in payload.get("key_fields", [])],
    )
    draft = get_draft_revision(session, mapping.id)
    if draft is None:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"mapping_id": mapping.id, "reason": "no_draft"},
        )
    entity_maps = [EntityMapCreate.model_validate(entry) for entry in draft.entity_maps]
    if any(
        entry.entity_type == entity_type
        and entry.db_schema == new_entity.db_schema
        and entry.table == table
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
    rel_maps = [RelMapCreate.model_validate(entry) for entry in draft.rel_maps]
    save_draft(
        session,
        mapping.id,
        MappingRevisionCreate(entity_maps=entity_maps, rel_maps=rel_maps),
        if_match=mapping.current_revision,
        if_edit_match=mapping.edit_revision,
    )


def _mapping_context(session: Session, mapping_id: int, datasource_id: int) -> dict:
    mapping = get_mapping(session, mapping_id)
    snap = get_latest_snapshot(session, datasource_id)
    draft = get_draft_revision(session, mapping_id)
    onto = session.get(Ontology, mapping.ontology_id)
    if snap is None or draft is None or onto is None:
        return {}
    ontology = _ontology_mapping_context(session, onto)
    return {
        "datasource_id": datasource_id,
        "metadata_snapshot_id": snap.id,
        "metadata_revision": snap.revision,
        "ontology": ontology,
    }


def _ontology_mapping_context(session: Session, onto: Ontology) -> dict:
    if onto.status == ResourceStatus.PUBLISHED and onto.current_revision > 0:
        snapshots = ontology_snapshot.load_ontology_snapshot(
            session, onto.id, onto.current_revision
        )
        onto_revision = session.scalar(
            select(OntologyRevision).where(
                OntologyRevision.ontology_id == onto.id,
                OntologyRevision.revision == onto.current_revision,
            )
        )
        types = [
            {
                "id": resource.id,
                "name": resource.name,
                "parents": sorted(resource.parent_ids),
                "props": sorted(
                    prop.name
                    for prop in ontology_snapshot.effective_datatype_props(
                        snapshots, resource.id
                    )
                ),
            }
            for resource in snapshots.values()
            if resource.kind in (ResourceKind.ENTITY, ResourceKind.ASSOC)
        ]
        return {
            "mode": "PUBLISHED",
            "revision": onto.current_revision,
            "resource_versions": onto_revision.resource_versions
            if onto_revision
            else {},
            "types": sorted(types, key=lambda entry: entry["id"]),
        }

    refs = list(
        session.scalars(
            select(OntologyResourceRef).where(
                OntologyResourceRef.ontology_id == onto.id
            )
        )
    )
    entries: dict[int, dict] = {}
    pins: dict[str, int] = {}
    for ref in refs:
        resource = session.get(ModelResource, ref.resource_id)
        if resource is None or resource.kind not in (
            ResourceKind.ENTITY,
            ResourceKind.ASSOC,
        ):
            continue
        pin = ref.pinned_revision or resource.current_revision
        if pin > 0:
            snapshot = ontology_snapshot.load_resource_snapshot(
                session, resource.id, pin
            )
            name = snapshot.name
            props = [prop.name for prop in snapshot.datatype_props]
            parents = snapshot.parent_ids
        else:
            name = resource.name
            props = list(
                session.scalars(
                    select(DatatypePropDetail.prop_name)
                    .join(
                        ResourceRef,
                        ResourceRef.target_id == DatatypePropDetail.resource_id,
                    )
                    .where(
                        ResourceRef.source_id == resource.id,
                        ResourceRef.role.in_(("data_prop", "assoc_attribute")),
                    )
                )
            )
            parents = list(
                session.scalars(
                    select(ResourceParent.parent_id).where(
                        ResourceParent.child_id == resource.id
                    )
                )
            )
        entries[resource.id] = {
            "id": resource.id,
            "name": name,
            "props": set(props),
            "parents": sorted(parents),
        }
        pins[str(resource.id)] = pin

    state: dict[int, int] = {}

    def effective_props(resource_id: int) -> set[str]:
        marker = state.get(resource_id, 0)
        if marker == 1:
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {"resource_id": resource_id, "reason": "inheritance_cycle"},
            )
        entry = entries.get(resource_id)
        if entry is None:
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {"resource_id": resource_id, "reason": "missing_parent_snapshot"},
            )
        if marker == 2:
            return entry["effective_props"]
        state[resource_id] = 1
        props = set(entry["props"])
        for parent_id in entry["parents"]:
            props.update(effective_props(parent_id))
        state[resource_id] = 2
        entry["effective_props"] = props
        return props

    types = [
        {
            "id": resource_id,
            "name": entry["name"],
            "parents": entry["parents"],
            "props": sorted(effective_props(resource_id)),
        }
        for resource_id, entry in sorted(entries.items())
    ]
    return {"mode": "DRAFT", "resource_versions": pins, "types": types}


def _validate_mapping_suggestion_sources(
    session: Session, context: dict, payload: dict
) -> None:
    snap = get_snapshot(session, int(context["metadata_snapshot_id"]))
    datasource_id = int(context["datasource_id"])
    if snap.datasource_id != datasource_id or snap.revision != int(
        context["metadata_revision"]
    ):
        raise KGError(
            ErrorCode.SUGGESTION_NOT_APPLICABLE,
            {"reason": "metadata_snapshot_mismatch"},
        )
    schema_name = str(payload.get("schema", "main"))
    table = str(payload.get("table", ""))
    columns = {
        column["name"]
        for schema in snap.catalog.get("schemas", [])
        if schema.get("schema", "main") == schema_name
        for source_table in schema.get("tables", [])
        if source_table.get("name") == table
        for column in source_table.get("columns", [])
    }
    type_entry = next(
        (
            entry
            for entry in context["ontology"]["types"]
            if entry["name"] == payload.get("entity_type")
        ),
        None,
    )
    if type_entry is None or not columns:
        raise KGError(
            ErrorCode.SUGGESTION_NOT_APPLICABLE, {"reason": "source_or_target_changed"}
        )
    for key in payload.get("key_fields", []):
        if not key or key not in columns:
            raise KGError(
                ErrorCode.SUGGESTION_NOT_APPLICABLE, {"reason": "source_key_changed"}
            )
    for field in payload.get("field_maps", []):
        if (
            not field.get("source_field")
            or field["source_field"] not in columns
            or field.get("target_attr") not in type_entry["props"]
        ):
            raise KGError(
                ErrorCode.SUGGESTION_NOT_APPLICABLE,
                {"reason": "source_or_target_changed"},
            )
