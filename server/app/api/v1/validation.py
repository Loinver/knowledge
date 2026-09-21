"""校验路由（H-50）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.validation_service import run_ontology_validation
from app.models.validation import ValidationReport

router = APIRouter(prefix="/validation", tags=["validation"])


@router.post("/ontologies/{ontology_id}")
def validate_ontology(
    ontology_id: int, session: Session = Depends(get_session)
) -> dict:
    report = run_ontology_validation(session, ontology_id)
    session.commit()
    return {
        "report_id": report.id,
        "scope": report.scope,
        "target_id": report.target_id,
        "summary": report.summary,
    }


@router.get("/reports/{report_id}")
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
        "summary": report.summary,
    }
