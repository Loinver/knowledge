"""owlrl 一致性执行器（A08 第三批）的真实引擎测试。

必测断言：
- 真实矛盾（不相交类有共同个体）→ VIOLATION，且错误消息进 raw
- 干净本体 → PASS
- 引擎无法解析 → NOT_RUN（引擎失败绝不改写成一致性结论）
"""

from __future__ import annotations

from app.models.enums import ValidationState
from app.semantics.rdflib_backend import RdflibBackend

_PREFIXES = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <https://example.org/> .
"""

_CONFLICT = (
    _PREFIXES
    + """
ex:A a owl:Class . ex:B a owl:Class . ex:C a owl:Class .
ex:C rdfs:subClassOf ex:A , ex:B .
ex:A owl:disjointWith ex:B .
ex:i1 a ex:C .
"""
)

_CLEAN = (
    _PREFIXES
    + """
ex:A a owl:Class . ex:B a owl:Class . ex:C a owl:Class .
ex:C rdfs:subClassOf ex:A .
ex:A owl:disjointWith ex:B .
ex:i1 a ex:C .
"""
)


def test_real_disjoint_conflict_is_violation() -> None:
    report = RdflibBackend().check_consistency(_CONFLICT)
    assert report.state is ValidationState.VIOLATION
    assert report.conforms is False
    assert "inconsistency" in report.results_text
    errors = report.raw["errors"]
    assert errors and "Disjoint" in errors[0]


def test_clean_ontology_is_pass() -> None:
    report = RdflibBackend().check_consistency(_CLEAN)
    assert report.state is ValidationState.PASS
    assert report.conforms is True


def test_unparsable_graph_is_not_run() -> None:
    report = RdflibBackend().check_consistency("this is not turtle @@@")
    assert report.state is ValidationState.NOT_RUN
