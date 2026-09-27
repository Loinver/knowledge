"""图谱形态推荐（第二批）：从冻结本体快照提取语义信号 → 推荐形态与理由。

推荐只依赖结构语义信号（自引用/传递/对称/带度量关联/日期属性/派生规则），
不依赖资源名、IRI 或表名——"改名但语义相同"的本体必须得到相同推荐。
理由以 i18n key + 结构化参数返回，前端按语言渲染；后端不返回中文句子。
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.extraction_service import resolve_graph
from app.domain.ontology_snapshot import (
    ResourceSnapshot,
    load_ontology_snapshot,
    relation_endpoints,
)
from app.models.data_access import Mapping, MappingRevision
from app.models.domain import OntologyRuleRef
from app.models.enums import ResourceKind
from app.models.extraction import ExtractionRun
from app.models.governance import Rule

# 每形态一条推荐：layout_id 与前端布局注册表一一对应。
LAYOUT_ORG_TREE = "org_tree"
LAYOUT_INDENT_TREE = "indent_tree"
LAYOUT_EQUITY_TREE = "equity_tree"
LAYOUT_CONTROL_CHAIN = "control_chain"
LAYOUT_FORCE = "force"
LAYOUT_PATH = "path"
LAYOUT_SCHEMA = "schema"
LAYOUT_SUPPLY_CHAIN = "supply_chain"
LAYOUT_TIMELINE = "timeline"

# 不依赖语义信号、任何图谱都可用的通用形态。
# path（G-12）与 diff（G-24）是查询/对比模式，不是布局，由前端单独提供。
GENERIC_LAYOUTS = [
    "type_grid",
    "ring",
    "force",
    "schema",
    "sunburst",
    "treemap",
    "pack",
]


def recommend_layouts(session: Session, graph_revision_id: int) -> dict:
    """读取当前图谱版本钉住的本体快照，输出语义信号与形态推荐。"""
    gr = resolve_graph(session, graph_revision_id)
    run = session.get(ExtractionRun, gr.run_id)
    if run is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"run_id": gr.run_id})
    rev = session.get(MappingRevision, run.mapping_revision_id)
    if rev is None:
        raise KGError(
            ErrorCode.REVISION_NOT_FOUND,
            {"mapping_revision_id": run.mapping_revision_id},
        )
    mapping = session.get(Mapping, rev.mapping_id)
    if mapping is None:
        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"mapping_id": rev.mapping_id})
    resources = list(
        load_ontology_snapshot(session, mapping.ontology_id, rev.onto_version).values()
    )
    signals = _extract_signals(resources)
    has_product_rule = _has_product_chain_rule(session, mapping.ontology_id)

    recommendations: list[dict] = []
    if signals["self_reference"] or signals["transitive"]:
        recommendations.append(
            {
                "layout_id": LAYOUT_ORG_TREE,
                "reason_key": "graph.reason.hierarchy",
                "reason_params": {"edge": signals["hierarchy_edge"] or ""},
            }
        )
        if signals["self_reference"]:
            recommendations.append(
                {
                    "layout_id": LAYOUT_INDENT_TREE,
                    "reason_key": "graph.reason.hierarchy",
                    "reason_params": {"edge": signals["hierarchy_edge"] or ""},
                }
            )
    if signals["measured_link"]:
        recommendations.append(
            {
                "layout_id": LAYOUT_EQUITY_TREE,
                "reason_key": "graph.reason.measuredLink",
                "reason_params": {"assoc": signals["measured_link"][0]["assoc"]},
            }
        )
        recommendations.append(
            {
                "layout_id": LAYOUT_SUPPLY_CHAIN,
                "reason_key": "graph.reason.measuredLink",
                "reason_params": {"assoc": signals["measured_link"][0]["assoc"]},
            }
        )
        if has_product_rule:
            recommendations.append(
                {
                    "layout_id": LAYOUT_CONTROL_CHAIN,
                    "reason_key": "graph.reason.productRule",
                    "reason_params": {},
                }
            )
    if signals["date_attrs"]:
        recommendations.append(
            {
                "layout_id": LAYOUT_TIMELINE,
                "reason_key": "graph.reason.dateAttr",
                "reason_params": {"count": len(signals["date_attrs"])},
            }
        )
    for layout_id in GENERIC_LAYOUTS:
        recommendations.append(
            {
                "layout_id": layout_id,
                "reason_key": "graph.reason.generic",
                "reason_params": {},
            }
        )
    return {
        "graph_revision_id": gr.id,
        "signals": signals,
        "recommendations": recommendations,
    }


def _extract_signals(resources: list[ResourceSnapshot]) -> dict:
    """结构语义信号提取。只看 kind、端点结构与 OWL 特征，不看名称。"""
    iri_by_id = {r.id: r.iri for r in resources}
    relations = [r for r in resources if r.kind == ResourceKind.OBJECT_PROP]
    assocs = {r.iri: r for r in resources if r.kind == ResourceKind.ASSOC}

    self_reference: list[dict] = []
    transitive = False
    symmetric = False
    hierarchy_edge = ""
    measured_link: list[dict] = []
    assoc_roles: list[dict] = []
    date_attrs: list[dict] = []
    assoc_linked_types: dict[str, set[str]] = {}

    for rel in relations:
        domain_iri, range_iri = relation_endpoints(rel, iri_by_id)
        owl = rel.owl or {}
        if owl.get("transitive"):
            transitive = True
            hierarchy_edge = hierarchy_edge or rel.iri
        if owl.get("symmetric"):
            symmetric = True
        if domain_iri and range_iri and domain_iri == range_iri:
            self_reference.append({"edge": rel.iri, "type": domain_iri})
            hierarchy_edge = hierarchy_edge or rel.iri
        for endpoint_iri in (domain_iri, range_iri):
            if endpoint_iri in assocs:
                linked = {
                    x
                    for x in (domain_iri, range_iri)
                    if x is not None and x != endpoint_iri
                }
                assoc_linked_types.setdefault(endpoint_iri, set()).update(linked)

    for iri, assoc in assocs.items():
        props = assoc.datatype_props
        linked = assoc_linked_types.get(iri, set())
        has_measure = any(p.datatype in {"decimal", "integer"} for p in props)
        has_role = any(p.datatype in {"string", "enum"} for p in props)
        if has_measure and len(linked) >= 1:
            measured_link.append({"assoc": iri, "linked_types": sorted(linked)})
        elif has_role and len(linked) >= 2:
            assoc_roles.append({"assoc": iri, "linked_types": sorted(linked)})

    for res in resources:
        if res.kind not in {ResourceKind.ENTITY, ResourceKind.ASSOC}:
            continue
        for prop in res.datatype_props:
            if prop.datatype == "date":
                date_attrs.append({"type": res.iri, "attr": prop.name})

    return {
        "self_reference": self_reference,
        "transitive": transitive,
        "symmetric": symmetric,
        "hierarchy_edge": hierarchy_edge,
        "measured_link": measured_link,
        "assoc_roles": assoc_roles,
        "date_attrs": date_attrs,
    }


def _has_product_chain_rule(session: Session, ontology_id: int) -> bool:
    """本体是否钉扎了 product_chain 派生规则（实际控制人链的计算依据）。"""
    rows = (
        session.execute(
            select(Rule.expression)
            .join(OntologyRuleRef, OntologyRuleRef.rule_id == Rule.id)
            .where(OntologyRuleRef.ontology_id == ontology_id)
        )
        .scalars()
        .all()
    )
    for expression in rows:
        try:
            if json.loads(expression).get("op") == "product_chain":
                return True
        except ValueError:
            continue
    return False
