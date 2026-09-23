"""校验路由（H-50 / H-51）。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Response
from rdflib import Graph, Literal, Namespace, URIRef
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.instance_validation_service import run_instance_validation
from app.domain.validation_service import run_ontology_validation
from app.models.validation import ValidationReport
from app.schemas.response import ApiResponse
from app.schemas.validation import ValidationReportOut, ValidationResultOut

router = APIRouter(prefix="/validation", tags=["validation"])


@router.post(
    "/ontologies/{ontology_id}", response_model=ApiResponse[ValidationReportOut]
)
def validate_ontology(
    ontology_id: int, session: Session = Depends(get_session)
) -> dict:
    report = run_ontology_validation(session, ontology_id)
    session.commit()
    return {
        "report_id": report.id,
        "scope": report.scope,
        "target_id": report.target_id,
        "target_revision": report.target_revision,
        "summary": report.summary,
    }


@router.post(
    "/graph/{graph_revision_id}", response_model=ApiResponse[ValidationReportOut]
)
def validate_graph(
    graph_revision_id: int, session: Session = Depends(get_session)
) -> dict:
    """对图谱版本运行实例层校验（H-51）。"""
    report = run_instance_validation(session, graph_revision_id)
    session.commit()
    return {
        "report_id": report.id,
        "scope": report.scope,
        "target_id": report.target_id,
        "target_revision": report.target_revision,
        "summary": report.summary,
    }


@router.get("/reports/{report_id}", response_model=ApiResponse[ValidationReportOut])
def get_report(report_id: int, session: Session = Depends(get_session)) -> dict:
    report = session.get(ValidationReport, report_id)
    if report is None:
        from app.core.error_codes import ErrorCode
        from app.core.errors import KGError

        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"report_id": report_id})
    return {
        "report_id": report.id,
        "scope": report.scope,
        "target_id": report.target_id,
        "target_revision": report.target_revision,
        "summary": report.summary,
    }


@router.get(
    "/reports/{report_id}/results",
    response_model=ApiResponse[list[ValidationResultOut]],
)
def get_report_results(
    report_id: int, session: Session = Depends(get_session)
) -> list[dict]:
    """取报告的逐项校验结果明细。"""
    report = session.get(ValidationReport, report_id)
    if report is None:
        from app.core.error_codes import ErrorCode
        from app.core.errors import KGError

        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"report_id": report_id})
    return [
        {
            "check_code": r.check_code,
            "state": r.state.value if hasattr(r.state, "value") else str(r.state),
            "focus_node": r.focus_node,
            "rule_id": r.rule_id,
            "detail": r.detail,
            "message": r.message,
        }
        for r in report.results
    ]


@router.get("/reports/{report_id}/export")
def export_report(
    report_id: int,
    rdf_format: str = Query("json", alias="format", pattern="^(json|turtle)$"),
    session: Session = Depends(get_session),
) -> Response:
    report = session.get(ValidationReport, report_id)
    if report is None:
        from app.core.error_codes import ErrorCode
        from app.core.errors import KGError

        raise KGError(ErrorCode.RESOURCE_NOT_FOUND, {"report_id": report_id})
    results = [
        {
            "check_code": result.check_code,
            "state": result.state.value,
            "focus_node": result.focus_node,
            "rule_id": result.rule_id,
            "detail": result.detail,
            "message": result.message,
        }
        for result in report.results
    ]
    payload = {
        "report_id": report.id,
        "scope": report.scope,
        "target_id": report.target_id,
        "target_revision": report.target_revision,
        "summary": report.summary,
        "results": results,
    }
    if rdf_format == "json":
        return Response(
            content=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="validation-{report.id}.json"'
                )
            },
        )
    graph = Graph()
    ns = Namespace("urn:knowledge:validation:")
    subject = URIRef(f"{ns}report-{report.id}")
    graph.add((subject, ns.scope, Literal(report.scope)))
    graph.add((subject, ns.targetId, Literal(report.target_id)))
    graph.add((subject, ns.targetRevision, Literal(report.target_revision)))
    graph.add(
        (
            subject,
            ns.summary,
            Literal(json.dumps(report.summary, ensure_ascii=False, sort_keys=True)),
        )
    )
    for result in results:
        item = URIRef(f"{subject}/result/{result['check_code']}")
        graph.add((subject, ns.result, item))
        graph.add((item, ns.checkCode, Literal(result["check_code"])))
        graph.add((item, ns.state, Literal(result["state"])))
        if result["focus_node"]:
            graph.add((item, ns.focusNode, Literal(result["focus_node"])))
    return Response(
        content=graph.serialize(format="turtle"),
        media_type="text/turtle",
        headers={
            "Content-Disposition": f'attachment; filename="validation-{report.id}.ttl"'
        },
    )
