"""语义适配层接口。

定义 parse / serialize / validate / reason 四个原语，RdflibBackend 是本地实现，
JenaRemoteBackend（M4）走同一接口。领域层只依赖此接口，不感知 rdflib 细节。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol, runtime_checkable

from app.models.enums import ValidationState

#: 序列化支持的 MIME。
SERIALIZER_TURTLE = "text/turtle"
SERIALIZER_JSONLD = "application/ld+json"

#: 解析支持的 MIME。
PARSER_TURTLE = "text/turtle"
PARSER_JSONLD = "application/ld+json"


@runtime_checkable
class SemanticBackend(Protocol):
    """语义后端契约。

    实现方负责将领域侧的 Turtle/JSON-LD 文本转成内部图、序列化回文本、
    运行 SHACL 校验与 OWL 推理。四态严格区分：未实现的能力返回
    ValidationState.NOT_RUN，绝不退化成 PASS。
    """

    def parse(self, data: str, *, rdf_format: str = PARSER_TURTLE) -> Any:
        """将文本解析为内部图对象。实现方可自由选择图表示。"""
        ...

    def serialize(self, graph: Any, *, rdf_format: str = SERIALIZER_TURTLE) -> str:
        """将内部图序列化为文本。往返不可丢 IRI 与字面量。"""
        ...

    def validate(
        self,
        data_graph: Any,
        *,
        shapes_graph: Any | None = None,
    ) -> ValidationReport:
        """用 SHACL 校验 data_graph，返回真实报告（非硬编码结论）。

        shapes_graph 缺省时用 rdflib SHACL 内建 shape 集。
        """
        ...

    def reason(self, data_graph: Any) -> ReasonReport:
        """运行最小推理（RDFS+OWL Horst），返回推断三元组。"""
        ...

    def check_consistency(
        self, data: str, *, rdf_format: str = PARSER_TURTLE
    ) -> ValidationReport:
        """对序列化的本体图运行 OWL 一致性检查，返回真实引擎结论。

        一致性检查是独立于最小推理的能力；后端不具备时应抛出
        NotImplementedError，由领域层转 NOT_RUN，绝不退化成 PASS。
        """
        ...

    def has_full_reasoner(self) -> bool:
        """是否具备 OWL 一致性检查能力。

        RdflibBackend 通过 owlrl 提供 OWL 2 RL 一致性闭包（含
        owl:Nothing 物化检测）；DL 完整推理仍超出范围，调用方在
        结果 detail 中如实标注推理谱系。
        """
        ...


class ValidationReport:
    """SHACL 校验报告（四态）。

    conforms 为 True 时 state=PASS，否则 state=VIOLATION；shapes_graph 为
    None 且后端无法确认是否需要 shape 时为 NA。NOT_RUN 由调用方在外层
    根据后端能力设置，本报告只承载真实引擎结论。
    """

    __slots__ = ("conforms", "raw", "results_text", "state")

    def __init__(
        self,
        *,
        state: ValidationState,
        conforms: bool,
        results_text: str,
        raw: Any = None,
    ) -> None:
        self.state = state
        self.conforms = conforms
        self.results_text = results_text
        self.raw = raw

    @property
    def is_pass(self) -> bool:
        return self.state is ValidationState.PASS

    @property
    def is_violation(self) -> bool:
        return self.state is ValidationState.VIOLATION

    def __repr__(self) -> str:
        return f"ValidationReport(state={self.state.value}, conforms={self.conforms})"


class ReasonReport:
    """推理报告。

    inferred 为推断得到的三元组集合（原数据图已有者不计入）。
    """

    __slots__ = ("inferred", "raw", "results_text", "state")

    def __init__(
        self,
        *,
        state: ValidationState,
        inferred: Iterable[tuple[Any, Any, Any]],
        results_text: str,
        raw: Any = None,
    ) -> None:
        self.state = state
        self.inferred: set[tuple[Any, Any, Any]] = set(inferred)
        self.results_text = results_text
        self.raw = raw

    def __repr__(self) -> str:
        return (
            f"ReasonReport(state={self.state.value}, n_inferred={len(self.inferred)})"
        )


__all__ = [
    "PARSER_JSONLD",
    "PARSER_TURTLE",
    "SERIALIZER_JSONLD",
    "SERIALIZER_TURTLE",
    "ReasonReport",
    "SemanticBackend",
    "ValidationReport",
]
