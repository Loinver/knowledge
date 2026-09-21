"""FastAPI 应用入口（M0 骨架）。

前后端一体：开发态由 Vite 代理 /api 到后端；生产态后端直接托管 `web/dist`，
一个端口同时提供页面与 API。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.api.v1.datasources import router as datasources_router
from app.api.v1.domains import router as domains_router
from app.api.v1.namespaces import router as namespaces_router
from app.api.v1.ontologies import router as ontologies_router
from app.api.v1.relations import router as relations_router
from app.api.v1.types import router as types_router
from app.api.v1.validation import router as validation_router
from app.core.db import Base, get_engine
from app.core.errors import install_error_handler

API_PREFIX = "/api/v1"
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"

app = FastAPI(
    title="Knowledge Platform",
    description="知识中台：本体建模 → 数据接入 → 映射配置 → 抽取执行 → 图谱与证据追溯",
    version="0.0.0",
)

install_error_handler(app)


@app.on_event("startup")
def _create_tables() -> None:
    """开发态自动建表（生产用 Alembic 迁移）。"""
    Base.metadata.create_all(get_engine())


app.include_router(namespaces_router, prefix=API_PREFIX)
app.include_router(ontologies_router, prefix=API_PREFIX)
app.include_router(datasources_router, prefix=API_PREFIX)
app.include_router(domains_router, prefix=API_PREFIX)
app.include_router(types_router, prefix=API_PREFIX)
app.include_router(relations_router, prefix=API_PREFIX)
app.include_router(validation_router, prefix=API_PREFIX)


class IriRequest(BaseModel):
    namespace: str
    name: str


class IriResponse(BaseModel):
    iri: str


class HealthResponse(BaseModel):
    status: str
    version: str


@app.get(f"{API_PREFIX}/health", response_model=HealthResponse)
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
