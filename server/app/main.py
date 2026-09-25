"""FastAPI 应用入口（M0 骨架）。

前后端一体：开发态由 Vite 代理 /api 到后端；生产态后端直接托管 `web/dist`，
一个端口同时提供页面与 API。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.api.errors import install_error_handler
from app.api.v1.accounts import router as accounts_router
from app.api.v1.auth import router as auth_router
from app.api.v1.clauses import router as clauses_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.datasources import router as datasources_router
from app.api.v1.deps import authorize_business_request
from app.api.v1.domains import router as domains_router
from app.api.v1.enum_dictionaries import (
    legacy_router as enum_legacy_router,
)
from app.api.v1.enum_dictionaries import (
    router as enum_dictionaries_router,
)
from app.api.v1.extraction import router as extraction_router
from app.api.v1.governance import router as governance_router
from app.api.v1.mapping_preview import router as mapping_preview_router
from app.api.v1.mappings import router as mappings_router
from app.api.v1.metadata import router as metadata_router
from app.api.v1.namespaces import router as namespaces_router
from app.api.v1.ontologies import router as ontologies_router
from app.api.v1.preview import router as preview_router
from app.api.v1.relations import router as relations_router
from app.api.v1.templates import router as templates_router
from app.api.v1.types import router as types_router
from app.api.v1.validation import router as validation_router
from app.core.config import get_settings
from app.core.db import Base, get_engine
from app.schemas.response import ApiResponse

API_PREFIX = "/api/v1"
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """开发态按配置建表，并在正常退出或启动失败时释放数据库连接。"""
    engine = get_engine()
    try:
        if get_settings().create_tables_on_startup:
            Base.metadata.create_all(engine)
        yield
    finally:
        engine.dispose()


app = FastAPI(
    title="Knowledge Platform",
    description="知识中台：本体建模 → 数据接入 → 映射配置 → 抽取执行 → 图谱与证据追溯",
    version="0.0.0",
    lifespan=lifespan,
)

install_error_handler(app)


business_router = APIRouter(
    prefix=API_PREFIX, dependencies=[Depends(authorize_business_request)]
)
business_router.include_router(namespaces_router)
business_router.include_router(ontologies_router)
business_router.include_router(datasources_router)
business_router.include_router(domains_router)
business_router.include_router(enum_dictionaries_router)
business_router.include_router(enum_legacy_router)
business_router.include_router(mappings_router)
business_router.include_router(mapping_preview_router)
business_router.include_router(metadata_router)
business_router.include_router(preview_router)
business_router.include_router(types_router)
business_router.include_router(templates_router)
business_router.include_router(relations_router)
business_router.include_router(validation_router)
business_router.include_router(extraction_router)
business_router.include_router(governance_router)
business_router.include_router(clauses_router)
app.include_router(business_router)
app.include_router(dashboard_router, prefix=API_PREFIX)
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(accounts_router, prefix=API_PREFIX)


class HealthResponse(BaseModel):
    status: str
    version: str


@app.get(f"{API_PREFIX}/health", response_model=ApiResponse[HealthResponse])
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=app.version)


def mount_spa(application: FastAPI) -> None:
    """构建产物存在时托管前端静态资源，实现单端口部署。"""
    if not WEB_DIST.is_dir():
        return
    application.mount(
        "/assets",
        StaticFiles(directory=WEB_DIST / "assets"),
        name="assets",
    )

    @application.get("/", include_in_schema=False)
    def spa_index() -> FileResponse:
        return FileResponse(WEB_DIST / "index.html")

    @application.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(WEB_DIST / "index.html")


mount_spa(app)
