"""Bounded offline execution of AUTO OWL RL and SHACL Core on frozen inputs.

The caller owns database snapshots and persistence. This module accepts only data,
does not load resources or contact services, and isolates parsing/engines in a
disposable process. Unsupported or failed execution is NOT_RUN; an applicable
rule earns PASS only after real execution. OWL results describe the combined TBox
consistency (open world), not database uniqueness or isolated rule attribution.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any, Never

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.errors import KGError
from app.models.enums import ResourceKind, ValidationState
from app.semantics.ontology_rdf import OntologyRdfMetadata, OntologyRdfResource

TIMEOUT_SECONDS = 45
MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_HITS = 200
_SLOTS = BoundedSemaphore(2)
_SERVER_ROOT = Path(__file__).resolve().parents[2]
_CLASSES = {ResourceKind.ENTITY, ResourceKind.ASSOC}


class OntologyRuleValidationResult(BaseModel):
    rule_id: int | None = None
    identifier: str
    revision: int | None = None
    language: str
    state: ValidationState
    hits: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class _Entity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    iri: str
    type_iri: str
    attrs: dict[str, Any] = Field(default_factory=dict)


class _Triple(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: int | None = None
    subject: str
    predicate: str
    object_: str


class _InstanceGraph(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    entities: list[_Entity]
    triples: list[_Triple] = Field(default_factory=list)


def _result(
    record: dict[str, Any], state: ValidationState, reason: str | None = None
) -> OntologyRuleValidationResult:
    payload = record.get("snapshot", record)
    payload = payload if isinstance(payload, dict) else record
    rule_id = record.get("rule_id", payload.get("id"))
    revision = record.get("revision", payload.get("revision"))
    return OntologyRuleValidationResult(
        rule_id=rule_id if type(rule_id) is int else None,
        identifier=str(
            payload.get("identifier", record.get("identifier", f"rule:{rule_id}"))
        ),
        revision=revision if type(revision) is int else None,
        language=str(payload.get("language", "UNKNOWN")),
        state=state,
        reason=reason,
    )


def validate_ontology_auto_rules(
    *,
    metadata: OntologyRdfMetadata,
    snapshots: dict[int, OntologyRdfResource],
    rules: list[dict[str, Any]],
    instance_graph: str | dict[str, Any],
    revision: int,
    rdf_format: str = "turtle",
) -> list[OntologyRuleValidationResult]:
    """Execute fixed AUTO rules; every returned hit has focus/detail/triple_ids.

    Structured data: entities[{iri,type_iri,attrs}], triples[{id?,subject,
    predicate,object_}]. Relationship predicates accept an unambiguous frozen name
    or IRI. Text must contain ABox statements only; imports/remote JSON-LD context
    and statements capable of changing the TBox or shapes are rejected.
    """

    def not_run(reason: str) -> list[OntologyRuleValidationResult]:
        return [_result(record, ValidationState.NOT_RUN, reason) for record in rules]

    try:
        request = json.dumps(
            {
                "metadata": metadata.model_dump(mode="json"),
                "snapshots": {
                    str(key): value.model_dump(mode="json")
                    for key, value in snapshots.items()
                },
                "rules": rules,
                "instance_graph": instance_graph,
                "revision": revision,
                "rdf_format": rdf_format,
            },
            allow_nan=False,
        )
    except (TypeError, ValueError):
        return not_run("invalid_execution_input")
    if len(request.encode("utf-8")) > MAX_INPUT_BYTES:
        return not_run("execution_input_too_large")
    if not _SLOTS.acquire(blocking=False):
        return not_run("rule_runner_busy")
    try:
        try:
            completed = subprocess.run(
                [sys.executable, "-B", "-m", "app.semantics.ontology_rule_validation"],
                input=request,
                capture_output=True,
                text=True,
                cwd=_SERVER_ROOT,
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return not_run("rule_runner_timeout")
        except OSError:
            return not_run("rule_runner_unavailable")
        if completed.returncode != 0:
            return not_run("rule_runner_failed")
        try:
            response = json.loads(completed.stdout)
            if "error" in response:
                return not_run(str(response["error"]))
            results = [
                OntologyRuleValidationResult.model_validate(value)
                for value in response["results"]
            ]
            if len(results) != len(rules):
                return not_run("invalid_runner_response")
            return results
        except (ValueError, TypeError, KeyError, ValidationError):
            return not_run("invalid_runner_response")
    finally:
        _SLOTS.release()


class _InvalidExecutionError(ValueError):
    pass


def _fail(reason: str) -> Never:
    raise _InvalidExecutionError(reason)


def _frozen_tbox(
    metadata: OntologyRdfMetadata,
    snapshots: dict[int, OntologyRdfResource],
    revision: int,
) -> Any:
    from rdflib import OWL, RDF, RDFS, SH, XSD, Graph

    from app.schemas.ontology import OntologyExportFormat
    from app.semantics.ontology_rdf import _parse_graph, serialize_ontology_rdf

    if type(revision) is not int or revision < 1:
        _fail("invalid_ontology_revision")
    resource_iris = {resource.iri for resource in snapshots.values()}
    if len(resource_iris) != len(snapshots):
        _fail("duplicate_snapshot_identity")
    if any(
        iri.startswith((str(OWL), str(RDF), str(RDFS), str(SH), str(XSD)))
        for iri in resource_iris
    ):
        _fail("reserved_snapshot_identity")
    for resource in snapshots.values():
        for parent in resource.parent_ids:
            if (
                parent not in snapshots
                or resource.kind not in _CLASSES
                or snapshots[parent].kind not in _CLASSES
            ):
                _fail("incomplete_snapshot_closure")
        for ref in resource.resource_refs:
            if ref.target_id not in snapshots:
                _fail("incomplete_snapshot_closure")
            target = snapshots[ref.target_id]
            valid = {
                "relation_domain": resource.kind == ResourceKind.OBJECT_PROP
                and target.kind in _CLASSES,
                "relation_range": resource.kind == ResourceKind.OBJECT_PROP
                and target.kind in _CLASSES,
                "inverse_of": resource.kind == target.kind == ResourceKind.OBJECT_PROP,
                "data_prop": resource.kind in _CLASSES
                and target.kind == ResourceKind.DATATYPE_PROP,
                "assoc_attribute": resource.kind == ResourceKind.ASSOC
                and target.kind == ResourceKind.DATATYPE_PROP,
                "assoc_resource": resource.kind == ResourceKind.OBJECT_PROP
                and target.kind == ResourceKind.ASSOC,
            }.get(ref.role, False)
            if not valid:
                _fail("invalid_snapshot_reference")
        if resource.kind in _CLASSES:
            _owned_properties(resource.iri, snapshots)
    exported = serialize_ontology_rdf(
        metadata, snapshots, revision=revision, rdf_format=OntologyExportFormat.TURTLE
    )
    graph = _parse_graph("turtle", exported)
    tbox = Graph()
    # Only formal asset axioms are needed by OWL; SHACL/property metadata stays
    # separate and cannot masquerade as instance data or additional rule shapes.
    for subject, predicate, obj in graph:
        if str(subject) in resource_iris and predicate in {
            RDF.type,
            RDFS.subClassOf,
            RDFS.domain,
            RDFS.range,
            OWL.inverseOf,
        }:
            tbox.add((subject, predicate, obj))
    return tbox


def _owned_properties(
    type_iri: str, snapshots: dict[int, OntologyRdfResource]
) -> dict[str, dict[str, Any]]:
    by_iri = {resource.iri: resource for resource in snapshots.values()}
    pending = [by_iri[type_iri]]
    seen: set[str] = set()
    aliases: dict[str, dict[str, Any]] = {}
    while pending:
        resource = pending.pop()
        if resource.iri in seen:
            continue
        seen.add(resource.iri)
        expected = {
            snapshots[ref.target_id].iri
            for ref in resource.resource_refs
            if ref.role in {"data_prop", "assoc_attribute"}
        }
        if expected != {detail.get("iri") for detail in resource.datatype_props}:
            _fail("incomplete_property_snapshot")
        for detail in resource.datatype_props:
            for alias in (detail.get("name"), detail.get("iri")):
                if not isinstance(alias, str):
                    _fail("invalid_property_snapshot")
                if alias in aliases and aliases[alias].get("iri") != detail.get("iri"):
                    _fail("ambiguous_attribute_name")
                aliases[alias] = detail
        pending.extend(snapshots[parent] for parent in resource.parent_ids)
    return aliases


def _instance_data(
    value: str | dict[str, Any],
    rdf_format: str,
    snapshots: dict[int, OntologyRdfResource],
    metadata: OntologyRdfMetadata,
) -> tuple[Any, list[_Triple]]:
    from rdflib import OWL, RDF, Graph, Literal, URIRef

    from app.semantics.ontology_rdf import _DATATYPES, _iri, _parse_graph
    from app.semantics.rule_examples import MAX_TEXT_BYTES, MAX_TRIPLES

    kinds = {resource.iri: resource.kind for resource in snapshots.values()}
    triples: list[_Triple] = []
    if isinstance(value, str):
        if rdf_format not in {"turtle", "json-ld"}:
            _fail("unsupported_instance_format")
        graph = _parse_graph("turtle" if rdf_format == "turtle" else "json-ld", value)
        if any(
            len(context)
            for context in graph.store.contexts()
            if context.identifier != graph.identifier
        ):
            _fail("named_instance_graph_not_supported")
    else:
        data = _InstanceGraph.model_validate(value)
        if len(data.entities) + len(data.triples) > MAX_TRIPLES:
            _fail("too_many_instance_records")
        graph = Graph()
        entity_types: dict[str, str] = {}
        for entity in data.entities:
            if kinds.get(entity.type_iri) not in _CLASSES:
                _fail("instance_type_not_frozen")
            if entity.iri in entity_types:
                _fail("duplicate_instance_identity")
            entity_types[entity.iri] = entity.type_iri
            graph.add((_iri(entity.iri), RDF.type, _iri(entity.type_iri)))
            owned = _owned_properties(entity.type_iri, snapshots)
            for name, raw in entity.attrs.items():
                if name not in owned:
                    _fail("attribute_not_frozen")
                detail = owned[name]
                datatype = detail.get("datatype")
                if datatype != "enum" and datatype not in _DATATYPES:
                    _fail("unsupported_property_datatype")
                values = raw if isinstance(raw, list) else [raw]
                if len(values) > MAX_TRIPLES:
                    _fail("too_many_attribute_values")
                for item in values:
                    if item is None:
                        continue
                    if type(item) not in {str, int, float, bool}:
                        _fail("unsupported_attribute_value")
                    graph.add(
                        (
                            _iri(entity.iri),
                            _iri(str(detail["iri"])),
                            Literal(item, datatype=_DATATYPES.get(str(datatype))),
                        )
                    )
        by_name: dict[str, list[str]] = {}
        for resource in snapshots.values():
            if resource.kind == ResourceKind.OBJECT_PROP and resource.name:
                by_name.setdefault(resource.name, []).append(resource.iri)
        for triple in data.triples:
            predicate = triple.predicate
            if predicate not in kinds:
                candidates = by_name.get(predicate, [])
                if len(candidates) != 1:
                    _fail("relation_predicate_not_frozen_or_ambiguous")
                predicate = candidates[0]
            if triple.subject not in entity_types or triple.object_ not in entity_types:
                _fail("unresolved_instance_endpoint")
            graph.add((_iri(triple.subject), _iri(predicate), _iri(triple.object_)))
            triples.append(triple.model_copy(update={"predicate": predicate}))
        if len(graph.serialize(format="turtle").encode("utf-8")) > MAX_TEXT_BYTES:
            _fail("instance_graph_too_large")
    if len(graph) > MAX_TRIPLES:
        _fail("too_many_instance_triples")
    for subject, rdf_predicate, obj in graph:
        if (
            not isinstance(subject, URIRef)
            or str(subject) in kinds
            or str(subject) == metadata.iri
        ):
            _fail("invalid_instance_subject")
        _iri(str(subject))
        if rdf_predicate == RDF.type:
            if not isinstance(obj, URIRef) or kinds.get(str(obj)) not in _CLASSES:
                _fail("instance_type_not_frozen")
        elif rdf_predicate in {OWL.sameAs, OWL.differentFrom}:
            if not isinstance(obj, URIRef):
                _fail("invalid_instance_identity_axiom")
        elif kinds.get(str(rdf_predicate)) == ResourceKind.OBJECT_PROP:
            if not isinstance(obj, URIRef) or str(obj) in kinds:
                _fail("invalid_instance_object")
        elif kinds.get(str(rdf_predicate)) == ResourceKind.DATATYPE_PROP:
            if not isinstance(obj, Literal) or obj.datatype not in {
                None,
                RDF.langString,
                *_DATATYPES.values(),
            }:
                _fail("unsupported_instance_literal")
        else:
            _fail("instance_predicate_not_frozen")
        if isinstance(obj, URIRef):
            _iri(str(obj))
    return graph, triples


def _hit(
    focus: str, detail: dict[str, Any], triples: list[_Triple], path: str | None = None
) -> dict[str, Any]:
    ids = sorted(
        {
            triple.id
            for triple in triples
            if triple.id is not None
            and (triple.subject == focus or triple.object_ == focus)
            and (path is None or triple.predicate == path)
        }
    )
    return {"focus": focus, "triple_ids": ids, "detail": detail}


def _owl_hits(
    graph: Any, individuals: set[Any], triples: list[_Triple]
) -> list[dict[str, Any]]:
    from rdflib import OWL, RDF

    hits: list[dict[str, Any]] = []
    for left, right in sorted(
        graph.subject_objects(OWL.disjointWith), key=lambda pair: tuple(map(str, pair))
    ):
        for focus in sorted(
            set(graph.subjects(RDF.type, left))
            & set(graph.subjects(RDF.type, right))
            & individuals,
            key=str,
        ):
            hits.append(
                _hit(
                    str(focus),
                    {
                        "reason": "owl_disjoint_class_conflict",
                        "types": [str(left), str(right)],
                    },
                    triples,
                )
            )
    for left, right in sorted(
        graph.subject_objects(OWL.differentFrom), key=lambda pair: tuple(map(str, pair))
    ):
        if (left, OWL.sameAs, right) in graph:
            for focus in {left, right} & individuals:
                hits.append(
                    _hit(
                        str(focus),
                        {
                            "reason": "owl_identity_conflict",
                            "individuals": [str(left), str(right)],
                        },
                        triples,
                    )
                )
    unique = {json.dumps(hit, sort_keys=True): hit for hit in hits}
    return [unique[key] for key in sorted(unique)][:MAX_HITS]


def _evaluate(request: dict[str, Any]) -> list[OntologyRuleValidationResult]:
    import owlrl
    import pyshacl
    from rdflib import RDF, SH, Graph, URIRef

    from app.semantics.ontology_rules import _rule_payload, compile_ontology_rules

    metadata = OntologyRdfMetadata.model_validate(request["metadata"])
    snapshots = {
        int(key): OntologyRdfResource.model_validate(value)
        for key, value in request["snapshots"].items()
    }
    base = _frozen_tbox(metadata, snapshots, request["revision"])
    data, triples = _instance_data(
        request["instance_graph"], request["rdf_format"], snapshots, metadata
    )
    kinds = {resource.iri: resource.kind for resource in snapshots.values()}
    records = request["rules"]
    results: list[OntologyRuleValidationResult] = []
    compiled: dict[int, Any] = {}
    payloads: dict[int, dict[str, Any]] = {}
    tbox = Graph() + base
    for index, record in enumerate(records):
        result = _result(record, ValidationState.NOT_RUN)
        results.append(result)
        try:
            payload = _rule_payload(record)
            if payload.get("execution") != "AUTO":
                result.reason = "manual_rule_not_executed"
                continue
            if payload.get("language") not in {"OWL", "SHACL"}:
                result.reason = "unsupported_rule_language"
                continue
            plan = compile_ontology_rules([record], kinds)
            compiled[index], payloads[index] = plan, payload
            tbox += plan.tbox
        except KGError as exc:
            result.reason = str(exc.params.get("reason", "invalid_rule_snapshot"))
    if not compiled:
        return results
    closure = tbox + data
    engine = owlrl.OWLRL_Semantics(closure, axioms=False, daxioms=False, rdfs=False)
    try:
        engine.closure()
        engine.flush_stored_triples()
    except Exception:
        for index in compiled:
            results[index].reason = "owl_engine_failed"
        return results
    errors = [str(error) for error in engine.error_messages]
    individuals = set(data.subjects())
    owl_hits = _owl_hits(closure, individuals, triples) if errors else []
    output_bytes = 0
    for index, plan in compiled.items():
        result, payload = results[index], payloads[index]
        target_iri = payload.get("target_iri")
        if not isinstance(target_iri, str):
            _fail("invalid_rule_target")
        target = URIRef(target_iri)
        if kinds[str(target)] in _CLASSES:
            focuses = set(closure.subjects(RDF.type, target)) & individuals
        else:
            focuses = set(closure.subjects(target, None)) & individuals
        result.detail = {
            "ontology_iri": metadata.iri,
            "ontology_revision": request["revision"],
            "target_iri": str(target),
            "target_count": len(focuses),
        }
        if result.language == "OWL":
            result.detail.update(
                {
                    "engine": "owlrl_owl2_rl",
                    "scope": "combined_tbox",
                    "errors": errors[:20],
                }
            )
            result.state = (
                ValidationState.VIOLATION
                if errors
                else ValidationState.PASS
                if focuses
                else ValidationState.NA
            )
            result.hits = owl_hits
            if errors and not owl_hits:
                result.reason = "owl_conflict_without_isolated_focus"
        elif not focuses:
            result.state = ValidationState.NA
        else:
            try:
                conforms, report, _ = pyshacl.validate(
                    closure,
                    shacl_graph=Graph() + plan.shapes,
                    inference="none",
                    advanced=False,
                    js=False,
                    do_owl_imports=False,
                    sparql_mode=False,
                    max_validation_depth=16,
                )
                if (
                    not isinstance(conforms, bool)
                    or not isinstance(report, Graph)
                    or (None, RDF.type, SH.ValidationReport) not in report
                ):
                    _fail("invalid_shacl_report")
                result.state = (
                    ValidationState.PASS if conforms else ValidationState.VIOLATION
                )
                result.detail["engine"] = "pyshacl_core"
                for item in sorted(
                    report.subjects(RDF.type, SH.ValidationResult), key=str
                ):
                    focus = report.value(item, SH.focusNode)
                    path = report.value(item, SH.resultPath)
                    inverse = (
                        report.value(path, SH.inversePath) if path is not None else None
                    )
                    path_text = str(inverse or path) if path is not None else None
                    result.hits.append(
                        _hit(
                            str(focus),
                            {
                                "path": path_text,
                                "inverse": inverse is not None,
                                "value": str(report.value(item, SH.value))
                                if report.value(item, SH.value) is not None
                                else None,
                                "constraint_component": str(
                                    report.value(item, SH.sourceConstraintComponent)
                                ),
                                "severity": str(report.value(item, SH.resultSeverity)),
                            },
                            triples,
                            path_text,
                        )
                    )
                    if len(result.hits) >= MAX_HITS:
                        result.detail["hits_truncated"] = True
                        break
            except Exception:
                result.state = ValidationState.NOT_RUN
                result.reason = "shacl_engine_failed"
                result.hits = []
        output_bytes += len(result.model_dump_json().encode("utf-8"))
        if output_bytes > MAX_OUTPUT_BYTES:
            _fail("execution_output_too_large")
    return results


def _worker() -> None:
    import socket

    def blocked(*args: Any, **kwargs: Any) -> Never:
        raise RuntimeError("rule execution forbids network")

    for method in ("connect", "connect_ex", "sendto"):
        setattr(socket.socket, method, blocked)
    socket.create_connection = blocked
    socket.getaddrinfo = blocked
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (12, 15))
        if sys.platform.startswith("linux"):
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    response: dict[str, Any]
    try:
        request = json.loads(sys.stdin.read(MAX_INPUT_BYTES + 1))
        results = _evaluate(request)
        response = {"results": [result.model_dump(mode="json") for result in results]}
    except KGError as exc:
        response = {"error": str(exc.params.get("reason", "invalid_execution_input"))}
    except _InvalidExecutionError as exc:
        response = {"error": str(exc)}
    except (ValueError, TypeError, KeyError, ValidationError):
        response = {"error": "invalid_execution_input"}
    encoded = json.dumps(response)
    if len(encoded.encode("utf-8")) > MAX_OUTPUT_BYTES:
        encoded = json.dumps({"error": "execution_output_too_large"})
    print(encoded)


if __name__ == "__main__":
    _worker()
