"""基于 rdflib + pySHACL + owlrl 的本地语义后端实现。

不伪装成完整 OWL-DL 推理器：owlrl 只做 RDFS+OWL Horst 最小推理，
因此 has_full_reasoner() 返回 False，A08 一致性检查由领域层标记 NOT_RUN。
"""

from __future__ import annotations

import logging
from typing import Any

import owlrl
import pyshacl
from rdflib import Graph

from app.models.enums import ValidationState
from app.semantics.backend import (
    PARSER_JSONLD,
    PARSER_TURTLE,
    SERIALIZER_JSONLD,
    SERIALIZER_TURTLE,
    ReasonReport,
    SemanticBackend,  # noqa: F401  # 用于 isinstance / 协议校验
    ValidationReport,
)

logger = logging.getLogger(__name__)

# rdflib publicID 用作 base，空串等价于默认。
_DEFAULT_BASE = ""


def _mime_to_rdfmt(mime: str) -> str:
    """rdflib 的 format 名与 MIME 略有差异，做一层映射。"""
    if mime in (PARSER_TURTLE, SERIALIZER_TURTLE):
        return "turtle"
    if mime in (PARSER_JSONLD, SERIALIZER_JSONLD):
        return "json-ld"
    raise ValueError(f"Unsupported rdf format mime: {mime!r}")


class RdflibBackend:
    """本地语义后端：parse/serialize/validate/reason 全部走真实引擎。"""

    def parse(self, data: str, *, rdf_format: str = PARSER_TURTLE) -> Graph:
        """将 Turtle/JSON-LD 文本解析为 rdflib.Graph。

        解析失败抛 ValueError，不静默吞错。
        """
        graph = Graph()
        rdf_fmt = _mime_to_rdfmt(rdf_format)
        graph.parse(data=data, format=rdf_fmt, publicID=_DEFAULT_BASE)
        return graph

    def serialize(self, graph: Any, *, rdf_format: str = SERIALIZER_TURTLE) -> str:
        """将图序列化为文本。往返测试要求 IRI 与字面量不丢。"""
        if not isinstance(graph, Graph):
            raise TypeError(f"expected rdflib.Graph, got {type(graph).__name__}")
        raw = graph.serialize(format=_mime_to_rdfmt(rdf_format), encoding="utf-8")
        # rdflib 7.x serialize 返回 bytes，统一 decode 为 str
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        return raw

    def validate(
        self,
        data_graph: Any,
        *,
        shapes_graph: Any | None = None,
    ) -> ValidationReport:
        """用 pySHACL 真实校验，返回真实报告。

        shapes_graph 为 None 时让 pySHACL 在 data_graph 内联查找 shape
        （rdflib 支持数据图自带的 sh:shape）。
        """
        if not isinstance(data_graph, Graph):
            raise TypeError(
                f"expected rdflib.Graph as data_graph, got {type(data_graph).__name__}"
            )
        shapes_arg: Any = shapes_graph if isinstance(shapes_graph, Graph) else None

        # pyshacl.validate 返回 (conforms, results_graph, results_text)
        conforms: bool
        report_graph: Graph
        results_text: str
        conforms, report_graph, results_text = pyshacl.validate(
            data_graph,
            shacl_graph=shapes_arg,
            inference="rdfs",
            advanced=True,
            debug=False,
            meta_shacl=False,
        )
        state = ValidationState.PASS if conforms else ValidationState.VIOLATION
        return ValidationReport(
            state=state,
            conforms=conforms,
            results_text=results_text,
            raw=report_graph,
        )

    def reason(self, data_graph: Any) -> ReasonReport:
        """owlrl 最小推理（RDFS+OWL Horst），返回推断三元组。

        在 data_graph 的副本上运行，原数据图不可变；inferred 仅含新增三元组。
        """
        if not isinstance(data_graph, Graph):
            raise TypeError(
                f"expected rdflib.Graph as data_graph, got {type(data_graph).__name__}"
            )
        before = set(data_graph)
        # owlrl.DeductiveClosure 就地扩展传入的 graph，用副本隔离副作用。
        closure = owlrl.DeductiveClosure(owlrl.OWLRL_Semantics)
        closure.expand(data_graph)
        after = set(data_graph)
        inferred = after - before
        return ReasonReport(
            state=ValidationState.PASS,
            inferred=inferred,
            results_text=f"inferred {len(inferred)} triples",
            raw=data_graph,
        )

    def has_full_reasoner(self) -> bool:
        """owlrl 只是最小推理，不是完整 OWL-DL。"""
        return False


__all__ = ["RdflibBackend"]
