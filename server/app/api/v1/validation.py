"""校验路由（H-50 / H-51）。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.v1.deps import semantic_backend
from app.core.db import get_session
from app.domain.instance_validation_service import run_instance_validation
from app.domain.validation_service import get_validation_report, run_ontology_validation
from app.models.validation import ValidationReport
from app.schemas.response import ApiResponse
from app.schemas.validation import ValidationReportOut, ValidationResultOut
from app.semantics.backend import SemanticBackend
from app.semantics.validation_rdf import serialize_validation_report

router = APIRouter(prefix="/validation", tags=["validation"])


def _report_out(report: ValidationReport) -> ValidationReportOut:
    return ValidationReportOut(
        report_id=report.id,
        scope=report.scope,
        target_id=report.target_id,
        target_revision=report.target_revision,
        summary=report.summary,
    )


def _results_out(report: ValidationReport) -> list[ValidationResultOut]:
    return [
        ValidationResultOut.model_validate(result, from_attributes=True)
        for result in report.results
    ]


@router.post(
    "/ontologies/{ontology_id}", response_model=ApiResponse[ValidationReportOut]
)
def validate_ontology(
    ontology_id: int,
    session: Session = Depends(get_session),
    backend: SemanticBackend = Depends(semantic_backend),
) -> ValidationReportOut:
    report = run_ontology_validation(session, ontology_id, backend=backend)
    session.commit()
    return _report_out(report)


@router.post(
    "/graph/{graph_revision_id}", response_model=ApiResponse[ValidationReportOut]
)
def validate_graph(
    graph_revision_id: int, session: Session = Depends(get_session)
) -> ValidationReportOut:
    """对图谱版本运行实例层校验（H-51）。"""
    report = run_instance_validation(session, graph_revision_id)
    session.commit()
    return _report_out(report)


@router.get("/reports/{report_id}", response_model=ApiResponse[ValidationReportOut])
def get_report(
    report_id: int, session: Session = Depends(get_session)
) -> ValidationReportOut:
    return _report_out(get_validation_report(session, report_id))


@router.get(
    "/reports/{report_id}/results",
    response_model=ApiResponse[list[ValidationResultOut]],
)
def get_report_results(
    report_id: int, session: Session = Depends(get_session)
) -> list[ValidationResultOut]:
    """取报告的逐项校验结果明细。"""
    return _results_out(get_validation_report(session, report_id))


@router.get("/reports/{report_id}/export")
def export_report(
    report_id: int,
    rdf_format: str = Query("json", alias="format", pattern="^(json|turtle)$"),
    session: Session = Depends(get_session),
) -> Response:
    report = get_validation_report(session, report_id)
    payload = {
        **_report_out(report).model_dump(),
        "results": [result.model_dump() for result in _results_out(report)],
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
    return Response(
        content=serialize_validation_report(payload),
        media_type="text/turtle",
        headers={
            "Content-Disposition": f'attachment; filename="validation-{report.id}.ttl"'
        },
    )
