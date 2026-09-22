"""Bounded, offline SHACL Core validation of user-supplied Turtle examples.

One targeted root shape represents one saved rule. The allowlist excludes
SPARQL, JavaScript, imports, custom validators, and SHACL advanced features.
Every parse and engine call happens in a disposable, time-limited process.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from threading import BoundedSemaphore
from typing import TYPE_CHECKING, Any

from app.core.error_codes import ErrorCode
from app.core.errors import KGError

if TYPE_CHECKING:
    from rdflib import Graph

    from app.schemas.governance import RuleCreate

MAX_TEXT_BYTES = 65536
MAX_TRIPLES = 2000
TIMEOUT_SECONDS = 6
_SLOTS = BoundedSemaphore(2)
_SERVER_ROOT = Path(__file__).resolve().parents[2]
_SHACL_CORE_TERMS = frozenset(
    [
        "NodeShape",
        "PropertyShape",
        "targetClass",
        "path",
        "property",
        "severity",
        "Info",
        "Warning",
        "Violation",
        "message",
        "name",
        "description",
        "order",
        "group",
        "minCount",
        "maxCount",
        "datatype",
        "class",
        "nodeKind",
        "BlankNode",
        "IRI",
        "Literal",
        "BlankNodeOrIRI",
        "BlankNodeOrLiteral",
        "IRIOrLiteral",
        "minExclusive",
        "minInclusive",
        "maxExclusive",
        "maxInclusive",
        "minLength",
        "maxLength",
        "pattern",
        "flags",
        "languageIn",
        "uniqueLang",
        "equals",
        "disjoint",
        "lessThan",
        "lessThanOrEquals",
        "and",
        "or",
        "not",
        "xone",
        "node",
        "qualifiedValueShape",
        "qualifiedMinCount",
        "qualifiedMaxCount",
        "qualifiedValueShapesDisjoint",
        "closed",
        "ignoredProperties",
        "hasValue",
        "in",
        "inversePath",
        "alternativePath",
        "zeroOrMorePath",
        "oneOrMorePath",
        "zeroOrOnePath",
    ]
)


def _invoke(payload: RuleCreate, *, execute: bool) -> dict[str, Any]:
    if not _SLOTS.acquire(blocking=False):
        raise KGError(ErrorCode.REASONER_UNAVAILABLE, {"reason": "rule_runner_busy"})
    try:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "app.semantics.rule_examples"],
                input=json.dumps({"payload": payload.model_dump(), "execute": execute}),
                capture_output=True,
                text=True,
                cwd=_SERVER_ROOT,
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            # subprocess.run kills and waits for its child before raising.
            raise KGError(
                ErrorCode.REASONER_UNAVAILABLE, {"reason": "rule_runner_timeout"}
            ) from exc
        except OSError as exc:
            raise KGError(
                ErrorCode.REASONER_UNAVAILABLE, {"reason": "rule_runner_unavailable"}
            ) from exc
        if result.returncode != 0:
            raise KGError(
                ErrorCode.REASONER_UNAVAILABLE, {"reason": "rule_runner_failed"}
            )
        try:
            output: dict[str, Any] = json.loads(result.stdout)
        except (ValueError, TypeError) as exc:
            raise KGError(
                ErrorCode.REASONER_UNAVAILABLE, {"reason": "invalid_runner_response"}
            ) from exc
        if "error" in output:
            raise KGError(ErrorCode(output["error"]), output["params"])
        return output
    finally:
        _SLOTS.release()


def inspect_examples(payload: RuleCreate) -> None:
    if payload.language == "SHACL":
        _invoke(payload, execute=False)


def run_examples(payload: RuleCreate) -> tuple[dict[str, Any], dict[str, Any]]:
    result = _invoke(payload, execute=True)
    return result["positive"], result["negative"]


def _invalid(field: str, reason: str) -> KGError:
    return KGError(ErrorCode.INVALID_REQUEST, {"field": field, "reason": reason})


def _parse(text: str, field: str) -> Graph:
    from rdflib import Graph

    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise _invalid(field, "turtle_too_large")
    try:
        graph = Graph().parse(data=text, format="turtle", publicID="urn:rule:base:")
    except Exception as exc:
        raise _invalid(field, "invalid_turtle") from exc
    if len(graph) > MAX_TRIPLES:
        raise _invalid(field, "too_many_triples")
    return graph


def _check_shapes(shapes: Graph, target_iri: str) -> None:
    from rdflib import OWL, RDF, RDFS, SH, URIRef

    # Check expanded RDF terms, so prefix aliases and Unicode escapes cannot bypass it.
    for subject, predicate, obj in shapes:
        for term in (subject, predicate, obj):
            if isinstance(term, URIRef) and (
                term == OWL.imports
                or (
                    str(term).startswith(str(SH))
                    and str(term)[len(str(SH)) :] not in _SHACL_CORE_TERMS
                )
            ):
                raise _invalid("expression", "unsupported_shacl_feature")
        if predicate == RDF.type and obj not in {
            SH.NodeShape,
            SH.PropertyShape,
            RDF.List,
        }:
            raise _invalid("expression", "unsupported_shape_type")
        if not str(predicate).startswith(str(SH)) and predicate not in {
            RDF.type,
            RDF.first,
            RDF.rest,
            RDFS.label,
            RDFS.comment,
        }:
            raise _invalid("expression", "unsupported_shape_predicate")
    targets = list(shapes.subject_objects(SH.targetClass))
    if (
        len(targets) != 1
        or targets[0][1] != URIRef(target_iri)
        or (targets[0][0], RDF.type, SH.NodeShape) not in shapes
    ):
        raise _invalid("expression", "single_target_class_required")


def _evaluate(payload: dict[str, Any], *, execute: bool) -> dict[str, Any]:
    import pyshacl
    from pyshacl.shapes_graph import ShapesGraph
    from rdflib import OWL, RDF, SH, Graph, URIRef

    shapes = _parse(payload["expression"], "expression")
    _check_shapes(shapes, payload["target_iri"])
    severity = {"INFO": SH.Info, "WARNING": SH.Warning, "VIOLATION": SH.Violation}[
        payload["severity"]
    ]
    if any(value != severity for value in shapes.objects(None, SH.severity)):
        raise _invalid("expression", "severity_conflict")
    examples = {
        field: _parse(payload[field], field)
        for field in ("positive_example", "negative_example")
    }
    for field, graph in examples.items():
        if any(graph.triples((None, OWL.imports, None))):
            raise _invalid(field, "unsupported_import")
        # A real explicit target instance is required in both examples. No inference
        # or injected focus nodes may turn a non-applicable shape into a passing test.
        if not any(graph.subjects(RDF.type, URIRef(payload["target_iri"]))):
            raise KGError(
                ErrorCode.VALIDATION_VIOLATION,
                {"field": field, "reason": "target_instance_required"},
            )
    options: dict[str, Any] = {
        "shacl_graph": shapes,
        "advanced": False,
        "js": False,
        "inference": "none",
        "do_owl_imports": False,
        "sparql_mode": False,
        "allow_infos": False,
        "allow_warnings": False,
        "max_validation_depth": 16,
    }
    try:
        # Validate the shape structure even when merely saving a rule.
        pyshacl.validate(Graph(), meta_shacl=True, **options)
        if not execute:
            return {}
        # Use the engine's own discovery, including implicit and nested shapes.
        # Explicit severity was checked above; only omitted defaults are filled in.
        for shape in ShapesGraph(shapes).shapes:
            shapes.add((shape.node, SH.severity, severity))
        results: dict[str, Any] = {}
        for field, graph in examples.items():
            conforms, report, report_text = pyshacl.validate(graph, **options)
            if not isinstance(report, Graph) or not isinstance(conforms, bool):
                raise _invalid("expression", "invalid_shacl_report")
            # Guard against a backend returning a boolean without a real report.
            if not any(report.subjects(RDF.type, SH.ValidationReport)):
                raise _invalid("expression", "invalid_shacl_report")
            results[field.removesuffix("_example")] = {
                "state": "PASS" if conforms else "VIOLATION",
                "conforms": conforms,
                "report_text": str(report_text)[:16000],
            }
        return results
    except KGError:
        raise
    except Exception as exc:
        raise _invalid("expression", "invalid_shacl_shape") from exc


def _worker() -> None:
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (4, 5))
        if sys.platform.startswith("linux"):
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    try:
        request = json.loads(sys.stdin.read(3 * MAX_TEXT_BYTES * 6 + 8192))
        result = _evaluate(request["payload"], execute=request["execute"])
    except KGError as exc:
        result = {"error": exc.code.value, "params": exc.params}
    print(json.dumps(result))


if __name__ == "__main__":
    _worker()
