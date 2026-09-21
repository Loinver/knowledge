"""映射编译预览路由（H-31）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.domain.mapping_compiler import compile_mapping
from app.schemas.mapping_compile import MappingPreviewResult

router = APIRouter(prefix="/mappings", tags=["mapping-preview"])


class CompileRequest(BaseModel):
    datasource_id: int
    limit: int = 20
    use_draft: bool = False


@router.post("/{mapping_id}/compile", response_model=MappingPreviewResult)
def compile_map(
    mapping_id: int,
    payload: CompileRequest,
    session: Session = Depends(get_session),
) -> MappingPreviewResult:
    result = compile_mapping(
        session,
        mapping_id,
        payload.datasource_id,
        payload.limit,
        payload.use_draft,
    )
    session.commit()
    return MappingPreviewResult(
        mapping_id=result["mapping_id"],
        revision=result["revision"],
        onto_version=result["onto_version"],
        entities=result["entities"],
        relations=result["relations"],
        summary=result["summary"],
    )
