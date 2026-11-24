"""本地本体一致性执行入口；调用方不依赖具体 RDF 引擎。"""

from __future__ import annotations

from app.semantics.backend import SemanticBackend, ValidationReport
from app.semantics.rdflib_backend import RdflibBackend


def check_ontology_consistency(
    content: str, backend: SemanticBackend | None = None
) -> ValidationReport:
    """发布使用本地引擎；测试/应用边界可以注入显式实现。"""
    executor = RdflibBackend() if backend is None else backend
    return executor.check_consistency(content)
