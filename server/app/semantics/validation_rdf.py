"""校验报告的 RDF 序列化，不读取数据库或决定校验结论。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from rdflib import Graph, Literal, Namespace, URIRef


def serialize_validation_report(payload: Mapping[str, Any]) -> str:
    """将报告传输数据序列化为 Turtle，保留逐项四态。"""
    graph = Graph()
    ns = Namespace("urn:knowledge:validation:")
    subject = URIRef(f"{ns}report-{payload['report_id']}")
    graph.add((subject, ns.scope, Literal(payload["scope"])))
    graph.add((subject, ns.targetId, Literal(payload["target_id"])))
    graph.add((subject, ns.targetRevision, Literal(payload["target_revision"])))
    graph.add(
        (
            subject,
            ns.summary,
            Literal(json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True)),
        )
    )
    for result in payload["results"]:
        item = URIRef(f"{subject}/result/{result['check_code']}")
        graph.add((subject, ns.result, item))
        graph.add((item, ns.checkCode, Literal(result["check_code"])))
        graph.add((item, ns.state, Literal(result["state"])))
        if result["focus_node"]:
            graph.add((item, ns.focusNode, Literal(result["focus_node"])))
    return graph.serialize(format="turtle")
