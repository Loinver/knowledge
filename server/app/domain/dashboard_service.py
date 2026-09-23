"""工作台统计：数据库聚合，避免分页截断及加载完整资源列表。"""

from __future__ import annotations

from sqlalchemy import ColumnElement, ScalarSelect, func, select
from sqlalchemy.orm import Session

from app.core.db import Base
from app.models.data_access import Datasource, Mapping
from app.models.domain import BusinessDomain, Ontology
from app.models.enums import ResourceKind, ResourceStatus
from app.models.extraction import ExtractionRun, GraphRevision, Quarantine
from app.models.resource import ModelResource


def _count(model: type[Base], *conditions: ColumnElement[bool]) -> ScalarSelect[int]:
    return select(func.count()).select_from(model).where(*conditions).scalar_subquery()


def get_stats(session: Session) -> dict[str, int | None]:
    """一次只读查询返回完整统计，当前图谱和其隔离记录使用同一快照。"""
    current = (
        select(GraphRevision.id, GraphRevision.run_id)
        .where(GraphRevision.is_current.is_(True))
        .cte("current_graph")
    )
    unpublished = (
        _count(
            ModelResource,
            ModelResource.kind.in_((ResourceKind.ENTITY, ResourceKind.OBJECT_PROP)),
            ModelResource.status == ResourceStatus.DRAFT,
        )
        + _count(BusinessDomain, BusinessDomain.status == ResourceStatus.DRAFT)
        + _count(Ontology, Ontology.status == ResourceStatus.DRAFT)
    )
    statement = select(
        _count(ModelResource, ModelResource.kind == ResourceKind.ENTITY).label(
            "entity_types"
        ),
        _count(ModelResource, ModelResource.kind == ResourceKind.OBJECT_PROP).label(
            "relation_types"
        ),
        _count(BusinessDomain).label("domains"),
        _count(Ontology).label("ontologies"),
        _count(Datasource).label("datasources"),
        _count(Mapping).label("mappings"),
        _count(ExtractionRun).label("runs"),
        select(current.c.id).scalar_subquery().label("current_graph_id"),
        _count(GraphRevision).label("result_set_count"),
        _count(
            Quarantine, Quarantine.run_id == select(current.c.run_id).scalar_subquery()
        ).label("quarantine_count"),
        unpublished.label("unpublished_count"),
    )
    return dict(session.execute(statement).one()._mapping)
