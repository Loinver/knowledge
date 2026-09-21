"""语义引擎 PoC 测试（H-04）。

覆盖：
- Turtle/JSON-LD 往返：IRI 与字面量不丢
- SHACL 真实校验：构造违反用例 → 报告含 violation（非硬编码）
- owlrl 推理：owl:subClassOf 传递可推出
- A08：未接完整推理器 → NOT_RUN，绝不被当 PASS
"""

from __future__ import annotations

import pytest
from app.models.enums import ValidationState
from app.semantics import (
    PARSER_JSONLD,
    PARSER_TURTLE,
    SERIALIZER_JSONLD,
    SERIALIZER_TURTLE,
    RdflibBackend,
    ReasonReport,
    SemanticBackend,
    ValidationReport,
)
from rdflib import RDF, Graph, Literal, Namespace
from rdflib.namespace import RDFS, SH

# 固定 Turtle 夹具，验收口径要求"不硬编码结论"。
CORE_NS = Namespace("https://example.org/core#")
SHAPES_NS = Namespace("https://example.org/shapes#")


@pytest.fixture()
def backend() -> RdflibBackend:
    return RdflibBackend()


# ---------------------------------------------------------------------------
# 协议契约
# ---------------------------------------------------------------------------


def test_rdflib_backend_satisfies_protocol(backend: RdflibBackend) -> None:
    """接口稳定，可替换实现：RdflibBackend 必须满足 SemanticBackend。"""
    assert isinstance(backend, SemanticBackend)


def test_has_full_reasoner_is_false_for_rdflib(backend: RdflibBackend) -> None:
    """owlrl 只是最小推理，不是完整 OWL-DL。"""
    assert backend.has_full_reasoner() is False


# ---------------------------------------------------------------------------
# 任务 11：Turtle / JSON-LD 往返：IRI 与字面量不丢
# ---------------------------------------------------------------------------


TURTLE_DATA = """
@prefix core: <https://example.org/core#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

core:Employee a core:EntityType ;
    core:label "员工"@zh , "Employee"@en ;
    core:code "EMP-001" ;
    core:active true ;
    core:sortIndex 3 .
"""


@pytest.mark.parametrize(
    ("serialize_fmt", "roundtrip_fmt"),
    [
        (SERIALIZER_TURTLE, PARSER_TURTLE),
        (SERIALIZER_JSONLD, PARSER_JSONLD),
        # Turtle -> JSON-LD -> Turtle 两跳往返
        ("cross", PARSER_TURTLE),
    ],
)
def test_roundtrip_preserves_iri_and_literals(
    backend: RdflibBackend,
    serialize_fmt: str,
    roundtrip_fmt: str,
) -> None:
    g1 = backend.parse(TURTLE_DATA, rdf_format=PARSER_TURTLE)
    if serialize_fmt == "cross":
        # 先转 JSON-LD，再从 JSON-LD 解析回图，最后序列化为 Turtle 比对
        jsonld_text = backend.serialize(g1, rdf_format=SERIALIZER_JSONLD)
        g2 = backend.parse(jsonld_text, rdf_format=PARSER_JSONLD)
        final_text = backend.serialize(g2, rdf_format=SERIALIZER_TURTLE)
        g_final = backend.parse(final_text, rdf_format=PARSER_TURTLE)
    else:
        text_out = backend.serialize(g1, rdf_format=serialize_fmt)
        g_final = backend.parse(text_out, rdf_format=roundtrip_fmt)

    # IRI 不丢
    assert (CORE_NS.Employee, RDF.type, CORE_NS.EntityType) in g_final
    # 字面量不丢（含语言标签与普通字面量、布尔、整型）
    assert (CORE_NS.Employee, CORE_NS.label, Literal("员工", lang="zh")) in g_final
    assert (CORE_NS.Employee, CORE_NS.label, Literal("Employee", lang="en")) in g_final
    assert (CORE_NS.Employee, CORE_NS.code, Literal("EMP-001")) in g_final
    assert (CORE_NS.Employee, CORE_NS.active, Literal(True)) in g_final
    assert (CORE_NS.Employee, CORE_NS.sortIndex, Literal(3)) in g_final


def test_parse_unsupported_format_raises(backend: RdflibBackend) -> None:
    with pytest.raises(ValueError):
        backend.parse("x", rdf_format="application/rdf+xml")


# ---------------------------------------------------------------------------
# 任务 12：SHACL 真实校验 —— 构造违反用例 → 报告含 violation
# ---------------------------------------------------------------------------


# Shape 要求 core:Employee 必须有 core:code 属性（minCount 1）。
SHACL_SHAPES = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix core: <https://example.org/core#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

core:EmployeeShape a sh:NodeShape ;
    sh:targetClass core:Employee ;
    sh:property [
        sh:path core:code ;
        sh:minCount 1 ;
        sh:datatype xsd:string ;
    ] .
"""

# 违反用例：Employee 没有 core:code。
VIOLATION_DATA = """
@prefix core: <https://example.org/core#> .

core:emp-001 a core:Employee ;
    core:label "张三" .
"""

# 合规用例：Employee 有 core:code。
CONFORMING_DATA = """
@prefix core: <https://example.org/core#> .

core:emp-001 a core:Employee ;
    core:label "张三" ;
    core:code "EMP-001" .
"""


def test_shacl_violation_report_is_real(backend: RdflibBackend) -> None:
    """构造违反用例 → 报告含 violation，且结论来自 pySHACL 而非硬编码。"""
    data = backend.parse(VIOLATION_DATA, rdf_format=PARSER_TURTLE)
    shapes = backend.parse(SHACL_SHAPES, rdf_format=PARSER_TURTLE)
    report = backend.validate(data, shapes_graph=shapes)

    assert isinstance(report, ValidationReport)
    assert report.state is ValidationState.VIOLATION
    assert report.conforms is False
    assert report.is_violation
    assert not report.is_pass
    # 报告正文必须提到 violation / 结果路径，证明是引擎产出而非硬编码
    assert "violation" in report.results_text.lower()
    assert "core:code" in report.results_text or "code" in report.results_text
    # 原始报告图必须存在且非空（pySHACL 真实产物）
    assert report.raw is not None
    assert isinstance(report.raw, Graph)
    # 报告图应包含 sh:ValidationReport 主体
    assert (None, RDF.type, SH.ValidationReport) in report.raw


def test_shacl_conforming_report_is_pass(backend: RdflibBackend) -> None:
    """合规用例 → PASS，conforms=True。"""
    data = backend.parse(CONFORMING_DATA, rdf_format=PARSER_TURTLE)
    shapes = backend.parse(SHACL_SHAPES, rdf_format=PARSER_TURTLE)
    report = backend.validate(data, shapes_graph=shapes)

    assert report.state is ValidationState.PASS
    assert report.conforms is True
    assert report.is_pass
    assert not report.is_violation


def test_shacl_report_is_not_hardcoded(backend: RdflibBackend) -> None:
    """同一后端、不同输入必须给出不同结论：证明报告来自真实引擎。"""
    shapes = backend.parse(SHACL_SHAPES, rdf_format=PARSER_TURTLE)
    bad = backend.validate(backend.parse(VIOLATION_DATA), shapes_graph=shapes)
    good = backend.validate(backend.parse(CONFORMING_DATA), shapes_graph=shapes)
    assert bad.state is not good.state
    assert bad.conforms != good.conforms


# ---------------------------------------------------------------------------
# 任务 13：owlrl 推理 —— owl:subClassOf 传递可推出
# ---------------------------------------------------------------------------


# Manager rdfs:subClassOf Employee；Employee rdfs:subClassOf Person。
# 传递后 Manager 应是 Person 的子类，且实例 a core:Person 可被推出。
SUBCLASS_CHAIN = """
@prefix core: <https://example.org/core#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

core:Employee rdfs:subClassOf core:Person .
core:Manager rdfs:subClassOf core:Employee .
core:emp_001 a core:Manager .
"""


def test_owlrl_infers_subclass_transitivity(backend: RdflibBackend) -> None:
    """owl:subClassOf 传递链可推出：Manager subClassOf Person。"""
    data = backend.parse(SUBCLASS_CHAIN, rdf_format=PARSER_TURTLE)
    report = backend.reason(data)

    assert isinstance(report, ReasonReport)
    assert report.state is ValidationState.PASS
    # 关键传递结论：Manager 是 Person 的子类
    assert (CORE_NS.Manager, RDFS.subClassOf, CORE_NS.Person) in report.inferred
    # 实例类型传递：emp-001 a Employee / Person 应被推出
    assert (CORE_NS.emp_001, RDF.type, CORE_NS.Employee) in report.inferred
    assert (CORE_NS.emp_001, RDF.type, CORE_NS.Person) in report.inferred


def test_reason_does_not_mutate_original_inferred_only(backend: RdflibBackend) -> None:
    """reason() 应返回推断三元组集合，原数据图原有三元组不计入 inferred。"""
    data = backend.parse(SUBCLASS_CHAIN, rdf_format=PARSER_TURTLE)
    before = set(data)
    report = backend.reason(data)
    # inferred 只含新增，不包含原有三元组
    assert before.isdisjoint(report.inferred)


# ---------------------------------------------------------------------------
# 任务 15：A08 四态不失真 —— NOT_RUN 绝不被当 PASS
# ---------------------------------------------------------------------------


def test_a08_not_run_when_no_full_reasoner(backend: RdflibBackend) -> None:
    """A08 OWL 一致性：未接完整推理器 → NOT_RUN，绝不能显示成 PASS。

    模拟领域层的判定逻辑：后端 has_full_reasoner()=False 时，
    A08 一致性检查项必须落 NOT_RUN，且 NOT_RUN 不等于 PASS。
    """
    if not backend.has_full_reasoner():
        a08_state = ValidationState.NOT_RUN
    else:
        # 占位：完整推理器接入后在此调用一致性检查
        a08_state = ValidationState.PASS

    assert a08_state is ValidationState.NOT_RUN
    # 四态不失真的核心断言：NOT_RUN 绝不被当 PASS
    assert a08_state is not ValidationState.PASS
    assert a08_state is not ValidationState.VIOLATION


@pytest.mark.parametrize(
    "state",
    [
        ValidationState.PASS,
        ValidationState.VIOLATION,
        ValidationState.NA,
        ValidationState.NOT_RUN,
    ],
)
def test_four_states_distinct(state: ValidationState) -> None:
    """四态两两不等：枚举值与字符串值都唯一。"""
    others = {
        ValidationState.PASS,
        ValidationState.VIOLATION,
        ValidationState.NA,
        ValidationState.NOT_RUN,
    }
    others.discard(state)
    assert state not in others
    # 字符串值也必须唯一
    assert state.value not in {o.value for o in others}


# ---------------------------------------------------------------------------
# 补充：validate 对非 Graph 输入抛 TypeError，不静默退化
# ---------------------------------------------------------------------------


def test_validate_rejects_non_graph(backend: RdflibBackend) -> None:
    with pytest.raises(TypeError):
        backend.validate("not a graph")  # type: ignore[arg-type]


def test_reason_rejects_non_graph(backend: RdflibBackend) -> None:
    with pytest.raises(TypeError):
        backend.reason("not a graph")  # type: ignore[arg-type]


def test_serialize_rejects_non_graph(backend: RdflibBackend) -> None:
    with pytest.raises(TypeError):
        backend.serialize("not a graph")  # type: ignore[arg-type]
