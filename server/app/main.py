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

from app.iri import build_iri, is_valid_name, is_valid_namespace

API_PREFIX = "/api/v1"
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"

app = FastAPI(
    title="Knowledge Platform",
    description="知识中台：本体建模 → 数据接入 → 映射配置 → 抽取执行 → 图谱与证据追溯",
    version="0.0.0",
)


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


@app.post(f"{API_PREFIX}/iri/build", response_model=IriResponse)
def build_resource_iri(payload: IriRequest) -> IriResponse:
    return IriResponse(
        iri=build_iri(payload.namespace, payload.name),
    )


@app.get(f"{API_PREFIX}/iri/validate")
def validate_resource_name(name: str, namespace: str = "") -> dict[str, bool]:
    return {
        "name": is_valid_name(name),
        "namespace": is_valid_namespace(namespace),
    }


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
