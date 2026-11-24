"""Pure candidate compilation; no model calls, DB, RDF execution or IO.

Catalogs are authorized, pinned JSON snapshots supplied by the application.
Their digest does not replace application-side authorization/freshness checks.
BLOCKED plans never expose executable partial operations. Inverse links are a
second allocation phase, not creation dependencies. COMPILED means compilation
only, never instance validation, standards conformance or publication.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.iri import NAME_PATTERN, PROPERTY_NAME_PATTERN, is_valid_namespace
from app.schemas.ontology_modeling_candidate import (
    CandidateErrorCode,
    CandidateParseError,
    Evidence,
    OntologyCandidate,
    ResourceCandidate,
    parse_candidate_json,
)

COMPILER_VERSION = "ontology-plan/1.1"
_PROPERTY_KINDS = {"DATA_PROPERTY", "OBJECT_PROPERTY"}
_UNSUPPORTED = {
    "HAS_KEY",
    "PROPERTY_CHAIN",
    "DATE_ORDER",
    "UNIQUE_TUPLE",
    "CONDITIONAL_REQUIRED",
}
_FEATURES = {"functional", "inverse_functional", "symmetric", "transitive"}


class _Namespace(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow")
    id: int = Field(gt=0)
    iri: str = Field(max_length=512)
    protected: bool


class _Asset(BaseModel):
    model_config = ConfigDict(strict=True, extra="allow")
    id: int = Field(gt=0)
    revision: int = Field(gt=0)
    kind: str
    iri: str
    name: str


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _refs(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if value.get("kind") in {"CANDIDATE", "CATALOG"}:
            return [value]
        return [ref for item in value.values() for ref in _refs(item)]
    if isinstance(value, list):
        return [ref for item in value for ref in _refs(item)]
    return []


def _normal_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _absolute_iri(iri: str) -> bool:
    try:
        return bool(urlsplit(iri).scheme) and not bool(re.search(r"[\s<>\"']", iri))
    except ValueError:
        return False


class _Compiler:
    def __init__(
        self,
        candidate: OntologyCandidate,
        namespace_catalog: Mapping[str, Mapping[str, object]],
        asset_catalog: Mapping[str, Mapping[str, object]],
        source_catalog: Mapping[str, Mapping[str, str]],
    ) -> None:
        self.candidate = candidate
        self.namespaces: dict[str, dict[str, Any]] = {}
        self.assets: dict[str, dict[str, Any]] = {}
        self.sources = source_catalog
        self.issues: list[dict[str, Any]] = []
        self.identities: dict[str, dict[str, Any]] = {}
        self.operations: dict[str, dict[str, Any]] = {}
        self.dependencies: dict[str, set[str]] = {}
        self.inverse_links: set[tuple[str, str]] = set()
        self.constraints: list[dict[str, Any]] = []
        self.axioms: list[dict[str, Any]] = []
        self.resources: dict[str, ResourceCandidate] = {}
        self._read_catalog(namespace_catalog, asset_catalog)

    def issue(
        self,
        code_suffix: str,
        candidate_id: str | None = None,
        *,
        not_run: bool = False,
        blocking: bool = True,
        **params: Any,
    ) -> None:
        if candidate_id is not None:
            params["candidate_id"] = candidate_id
        self.issues.append(
            {
                "code": CandidateErrorCode(f"KG.CANDIDATE_{code_suffix}").value,
                "params": params,
                "state": "NOT_RUN" if not_run else "VIOLATION",
                "blocking": blocking,
            }
        )

    def _read_catalog(
        self,
        namespaces: Mapping[str, Mapping[str, object]],
        assets: Mapping[str, Mapping[str, object]],
    ) -> None:
        handle_pattern = r"[A-Za-z][A-Za-z0-9:_-]{0,127}"
        seen_ids: dict[tuple[str, int], dict[str, Any]] = {}
        for category, catalog, model, destination in (
            ("namespace", namespaces, _Namespace, self.namespaces),
            ("asset", assets, _Asset, self.assets),
        ):
            for handle, record in sorted(catalog.items()):
                try:
                    if not re.fullmatch(handle_pattern, handle):
                        raise ValueError("invalid_handle")
                    value = model.model_validate(dict(record)).model_dump()
                    if not _absolute_iri(value["iri"]):
                        raise ValueError("invalid_iri")
                    if category == "namespace" and not is_valid_namespace(value["iri"]):
                        raise ValueError("invalid_namespace")
                    if category == "asset" and (
                        value["kind"] not in {"CLASS", *_PROPERTY_KINDS}
                        or not value["name"].strip()
                    ):
                        raise ValueError("invalid_asset")
                    key = (category, value["id"])
                    if key in seen_ids and seen_ids[key] != value:
                        raise ValueError("inconsistent_alias")
                    seen_ids[key] = value
                    destination[handle] = value
                except (ValidationError, ValueError, TypeError):
                    self.issue("INVALID_CATALOG", handle=handle, catalog=category)
        for source, spans in sorted(self.sources.items()):
            if not re.fullmatch(handle_pattern, source) or not isinstance(
                spans, Mapping
            ):
                self.issue("INVALID_SOURCE", source_handle=source)
                continue
            for span, text in sorted(spans.items()):
                if (
                    not re.fullmatch(handle_pattern, span)
                    or not isinstance(text, str)
                    or not text.strip()
                ):
                    self.issue(
                        "INVALID_SOURCE_SPAN", source_handle=source, span_handle=span
                    )

    def resolve(
        self,
        ref: dict[str, Any],
        expected: set[str],
        candidate_id: str,
    ) -> dict[str, Any] | None:
        key = ref["candidate_id"] if ref["kind"] == "CANDIDATE" else ref["handle"]
        value = (
            self.identities.get(key)
            if ref["kind"] == "CANDIDATE"
            else self.assets.get(key)
        )
        if value is None:
            # A known, not-yet-allocated data property is not an unknown class.
            item = self.resources.get(key) if ref["kind"] == "CANDIDATE" else None
            declared_kind = (
                item.spec.expected_kind
                if item is not None and item.spec.kind == "REUSE"
                else {
                    "NEW_CLASS": "CLASS",
                    "NEW_DATA_PROPERTY": "DATA_PROPERTY",
                    "NEW_OBJECT_PROPERTY": "OBJECT_PROPERTY",
                }.get(item.spec.kind if item is not None else "")
            )
            if declared_kind is not None and declared_kind not in expected:
                self.issue(
                    "REFERENCE_KIND",
                    candidate_id,
                    reference=key,
                    expected=sorted(expected),
                    actual=declared_kind,
                )
            else:
                self.issue("UNKNOWN_REFERENCE", candidate_id, reference=key)
        elif value["kind"] not in expected:
            self.issue(
                "REFERENCE_KIND",
                candidate_id,
                reference=key,
                expected=sorted(expected),
                actual=value["kind"],
            )
            value = None
        return value

    def prepare(self) -> None:
        items: list[Any] = [
            *self.candidate.resources,
            *self.candidate.axioms,
            *self.candidate.constraints,
        ]
        ids: set[str] = set()
        for item in items:
            cid = item.candidate_id
            if cid in ids:
                self.issue("DUPLICATE_ID", cid)
            ids.add(cid)
            self.dependencies[cid] = set()
        self.resources = {item.candidate_id: item for item in self.candidate.resources}
        # Allocate class/object-property identities before owner-scoped data properties.
        for item in self.candidate.resources:
            spec = item.spec.model_dump(by_alias=True)
            cid, kind = item.candidate_id, spec["kind"]
            if kind == "REUSE":
                asset = self.resolve(
                    {"kind": "CATALOG", "handle": spec["handle"]},
                    {spec["expected_kind"]},
                    cid,
                )
                if asset is not None:
                    self.identities[cid] = dict(asset)
                    self.operations[cid] = {
                        "candidate_id": cid,
                        "kind": "REUSE",
                        "handle": spec["handle"],
                        "id": asset["id"],
                        "revision": asset["revision"],
                        "expected_kind": asset["kind"],
                        "iri": asset["iri"],
                        "attach_to_ontology": spec["attach_to_ontology"],
                    }
                continue
            namespace = self.namespaces.get(spec["namespace_handle"])
            if namespace is None:
                self.issue("UNKNOWN_NAMESPACE", cid, handle=spec["namespace_handle"])
                continue
            if namespace["protected"]:
                self.issue("PROTECTED_NAMESPACE", cid, handle=spec["namespace_handle"])
            name = spec["local_name"]
            pattern = NAME_PATTERN if kind == "NEW_CLASS" else PROPERTY_NAME_PATTERN
            if not pattern.fullmatch(name):
                self.issue("INVALID_NAME", cid, name=name)
            if kind != "NEW_DATA_PROPERTY":
                identity = {
                    "kind": "CLASS" if kind == "NEW_CLASS" else "OBJECT_PROPERTY",
                    "name": name,
                    "iri": namespace["iri"] + name,
                    "namespace_handle": spec["namespace_handle"],
                }
                self.identities[cid] = identity
                self.operations[cid] = {
                    **identity,
                    "kind": kind,
                    "candidate_id": cid,
                    "namespace_id": namespace["id"],
                    "metadata": spec["metadata"],
                }
        for item in self.candidate.resources:
            spec, cid = item.spec.model_dump(by_alias=True), item.candidate_id
            if spec["kind"] != "NEW_DATA_PROPERTY":
                continue
            owner = self.resolve(spec["owner"], {"CLASS"}, cid)
            owner_candidate = self.resources.get(spec["owner"].get("candidate_id", ""))
            if owner_candidate is None or owner_candidate.spec.kind != "NEW_CLASS":
                self.issue(
                    "UNSUPPORTED",
                    cid,
                    not_run=True,
                    construct="DATA_PROPERTY_OWNER_REUSE",
                )
                continue
            namespace = self.namespaces.get(spec["namespace_handle"])
            if owner is None or namespace is None:
                continue
            if spec["namespace_handle"] != owner.get("namespace_handle"):
                self.issue("OWNER_NAMESPACE", cid)
            identity = {
                "kind": "DATA_PROPERTY",
                "name": owner["name"] + "." + spec["local_name"],
                "iri": owner["iri"] + "/" + spec["local_name"],
                "owner_iri": owner["iri"],
                "datatype": spec["datatype"],
            }
            self.identities[cid] = identity
            self.operations[cid] = {
                **identity,
                "kind": "NEW_DATA_PROPERTY",
                "candidate_id": cid,
                "namespace_id": namespace["id"],
                "metadata": spec["metadata"],
                "local_name": spec["local_name"],
            }
        self._evidence_and_dependencies(items, ids)
        for cid, identity in self.identities.items():
            if self.resources[cid].spec.kind == "REUSE":
                continue
            for field, limit in (("name", 128), ("iri", 640)):
                if len(identity[field]) > limit:
                    self.issue("INVALID_NAME", cid, field=field, max_length=limit)
        self._duplicates()

    def _evidence_and_dependencies(self, items: list[Any], ids: set[str]) -> None:
        questions: dict[str, Any] = {}
        for question in self.candidate.questions:
            if question.id in questions:
                self.issue("DUPLICATE_QUESTION", question_id=question.id)
            questions[question.id] = question
            if len(set(question.related_candidate_ids)) != len(
                question.related_candidate_ids
            ):
                self.issue("DUPLICATE_REFERENCE", question_id=question.id)
            for cid in question.related_candidate_ids:
                if cid not in ids:
                    self.issue(
                        "UNKNOWN_QUESTION_CANDIDATE", cid, question_id=question.id
                    )
            if question.blocking:
                self.issue("UNRESOLVED_QUESTION", not_run=True, question_id=question.id)
        for item in items:
            cid, spec = item.candidate_id, item.spec.model_dump(by_alias=True)
            # All references are validated, including unsupported AST branches.
            for ref in _refs(spec):
                self.resolve(ref, {"CLASS", *_PROPERTY_KINDS}, cid)
            creation_spec = {k: v for k, v in spec.items() if k != "inverse_of"}
            references = _refs(creation_spec)
            if hasattr(item, "target_class"):
                references.extend(_refs(item.target_class.model_dump()))
            self.dependencies[cid].update(
                ref["candidate_id"] for ref in references if ref["kind"] == "CANDIDATE"
            )
            self.check_evidence(item.evidence, cid, ids, questions)
        if self.candidate.ontology_metadata is not None:
            self.check_evidence(
                self.candidate.ontology_metadata.evidence, None, ids, questions
            )
        # Model-declared inverse pair dependencies are removed only after the
        # actual inverse relation is checked separately; all other cycles block.
        for cid, item in self.resources.items():
            spec = item.spec.model_dump(by_alias=True)
            if spec["kind"] == "NEW_OBJECT_PROPERTY" and spec["inverse_of"] is not None:
                inverse = spec["inverse_of"]
                if inverse["kind"] == "CANDIDATE" and inverse["candidate_id"] != cid:
                    other = self.resources.get(inverse["candidate_id"])
                    if other is not None and other.spec.kind == "NEW_OBJECT_PROPERTY":
                        self.dependencies[cid].discard(inverse["candidate_id"])

    def check_evidence(
        self,
        evidence: Evidence,
        cid: str | None,
        ids: set[str],
        questions: dict[str, Any],
    ) -> None:
        refs = [(ref.source_handle, ref.span_handle) for ref in evidence.source_refs]
        for sequence in (refs, evidence.depends_on, evidence.uncertainty_ids):
            if len(set(sequence)) != len(sequence):
                self.issue("DUPLICATE_EVIDENCE_REFERENCE", cid)
        for source, span in refs:
            text = self.sources.get(source, {}).get(span)
            if not isinstance(text, str) or not text.strip():
                self.issue(
                    "UNKNOWN_SOURCE_SPAN", cid, source_handle=source, span_handle=span
                )
        for dep in evidence.depends_on:
            if dep not in ids:
                self.issue("UNKNOWN_DEPENDENCY", cid, dependency=dep)
            if cid is not None:
                self.dependencies[cid].add(dep)
        for question_id in evidence.uncertainty_ids:
            question = questions.get(question_id)
            if question is None:
                self.issue("UNKNOWN_QUESTION", cid, question_id=question_id)
            elif cid is not None and cid not in question.related_candidate_ids:
                self.issue("QUESTION_ASSOCIATION", cid, question_id=question_id)
            # The model cannot label unresolved uncertainty nonblocking.
            self.issue(
                "UNRESOLVED_UNCERTAINTY", cid, not_run=True, question_id=question_id
            )

    def _duplicates(self) -> None:
        iris: dict[str, str] = {}
        names: dict[str, str] = {}
        words: dict[tuple[str, str, str], str] = {}
        for cid, identity in sorted(self.identities.items()):
            item = self.resources[cid]
            spec = item.spec.model_dump(by_alias=True)
            if spec["kind"] == "REUSE":
                # Repeated attachment of the same resource is also explicit.
                for old_cid, old in self.identities.items():
                    if old_cid < cid and old["iri"] == identity["iri"]:
                        self.issue(
                            "DUPLICATE_RESOURCE",
                            cid,
                            other=old_cid,
                            iri=identity["iri"],
                        )
                continue
            for field, index in (("iri", iris), ("name", names)):
                value = identity[field]
                if value in index:
                    self.issue(
                        "DUPLICATE_RESOURCE", cid, other=index[value], field=field
                    )
                index[value] = cid
                for handle, asset in self.assets.items():
                    if asset[field] == value:
                        self.issue(
                            "NEW_REQUIRES_REUSE", cid, handle=handle, field=field
                        )
            metadata = spec["metadata"]
            texts = [
                (language, text)
                for language, text in metadata["labels"].items()
                if text
            ] + [
                (synonym["language"], synonym["text"])
                for synonym in metadata["synonyms"]
            ]
            for language, text in texts:
                key = (identity["kind"], language, _normal_text(text))
                if key in words and words[key] != cid:
                    self.issue(
                        "POSSIBLE_SYNONYM",
                        cid,
                        not_run=True,
                        other=words[key],
                        language=language,
                    )
                words[key] = cid
                for handle, asset in self.assets.items():
                    existing = asset.get("metadata") or {}
                    labels = (
                        existing.get("labels", {}) if isinstance(existing, dict) else {}
                    )
                    aliases = (
                        existing.get("synonyms", [])
                        if isinstance(existing, dict)
                        else []
                    )
                    candidates = (
                        [labels.get(language)] if isinstance(labels, dict) else []
                    )
                    candidates += [
                        s.get("text")
                        for s in aliases
                        if isinstance(s, dict) and s.get("language") == language
                    ]
                    if asset["kind"] == identity["kind"] and any(
                        isinstance(t, str) and _normal_text(t) == key[2]
                        for t in candidates
                    ):
                        self.issue(
                            "POSSIBLE_SYNONYM",
                            cid,
                            not_run=True,
                            handle=handle,
                            language=language,
                        )

    def class_expression(self, expression: dict[str, Any], cid: str) -> list[str]:
        if expression["mode"] != "ONE":
            self.issue("UNSUPPORTED", cid, not_run=True, construct=expression["mode"])
        values = [self.resolve(ref, {"CLASS"}, cid) for ref in expression["refs"]]
        iris = [value["iri"] for value in values if value is not None]
        if len(set(iris)) != len(iris):
            self.issue("DUPLICATE_REFERENCE", cid)
        return iris

    def resource_details(self) -> None:
        for cid, item in sorted(self.resources.items()):
            spec = item.spec.model_dump(by_alias=True)
            operation, identity = self.operations.get(cid), self.identities.get(cid)
            if operation is None or identity is None:
                continue
            if spec["kind"] == "NEW_CLASS":
                parents = [self.resolve(ref, {"CLASS"}, cid) for ref in spec["parents"]]
                iris = [parent["iri"] for parent in parents if parent is not None]
                if len(set(iris)) != len(iris):
                    self.issue("DUPLICATE_REFERENCE", cid)
                if identity["iri"] in iris:
                    self.issue("INHERITANCE_CYCLE", cid)
                operation["parents"] = iris
                identity["parents"] = iris
            elif spec["kind"] == "NEW_OBJECT_PROPERTY":
                domain, range_ = (
                    self.class_expression(spec["domain"], cid),
                    self.class_expression(spec["range"], cid),
                )
                if len(domain) == len(range_) == 1:
                    identity.update(domain_iri=domain[0], range_iri=range_[0])
                    operation.update(domain_iri=domain[0], range_iri=range_[0])
                features = spec["features"]
                if (features["symmetric"] and features["asymmetric"]) or (
                    features["reflexive"] and features["irreflexive"]
                ):
                    self.issue("FEATURE_CONFLICT", cid)
                for feature, enabled in features.items():
                    if enabled and feature not in _FEATURES:
                        self.issue("UNSUPPORTED", cid, not_run=True, construct=feature)
                operation["features"] = {
                    key: features[key] for key in sorted(_FEATURES)
                }
                identity["features"] = operation["features"]
        paired: dict[str, str] = {}
        for cid, item in sorted(self.resources.items()):
            spec = item.spec.model_dump(by_alias=True)
            if spec["kind"] != "NEW_OBJECT_PROPERTY" or spec["inverse_of"] is None:
                continue
            identity = self.identities.get(cid)
            other = self.resolve(spec["inverse_of"], {"OBJECT_PROPERTY"}, cid)
            if identity is None or other is None:
                continue
            left, right = identity["iri"], other["iri"]
            for operand, inverse_iri in ((left, right), (right, left)):
                if operand in paired and paired[operand] != inverse_iri:
                    self.issue("INVERSE_CONFLICT", cid)
                paired[operand] = inverse_iri
            if left == right:
                self.issue("UNSUPPORTED", cid, not_run=True, construct="SELF_INVERSE")
            for a, b in (("domain_iri", "range_iri"), ("range_iri", "domain_iri")):
                if a not in identity or b not in other:
                    self.issue("MISSING_PROPERTY_CONTEXT", cid, not_run=True, field=b)
                elif identity[a] != other[b]:
                    self.issue("INVERSE_ENDPOINTS", cid)
            if spec["inverse_of"]["kind"] == "CANDIDATE":
                other_item = self.resources.get(spec["inverse_of"]["candidate_id"])
                if other_item and other_item.spec.kind == "NEW_OBJECT_PROPERTY":
                    inverse = other_item.spec.model_dump(by_alias=True)["inverse_of"]
                    if inverse is not None:
                        back = self.resolve(inverse, {"OBJECT_PROPERTY"}, cid)
                        if back is not None and back["iri"] != left:
                            self.issue("INVERSE_CONFLICT", cid)
            if other.get("id") is not None:
                # Connecting a catalog inverse would edit that existing asset.
                self.issue(
                    "UNSUPPORTED", cid, not_run=True, construct="INVERSE_REUSE_EDIT"
                )
            self.inverse_links.add(tuple(sorted((left, right))))

    def _is_subclass(self, child: str, parent: str) -> bool:
        pending, seen = [child], set()
        classes = {
            identity["iri"]: identity
            for identity in [*self.assets.values(), *self.identities.values()]
            if identity["kind"] == "CLASS"
        }
        while pending:
            current = pending.pop()
            if current == parent:
                return True
            if current in seen:
                continue
            seen.add(current)
            ancestors = classes.get(current, {}).get("parents", [])
            if isinstance(ancestors, list):
                pending.extend(p for p in ancestors if isinstance(p, str))
        return False

    def path(
        self, path: dict[str, Any], target: dict[str, Any] | None, cid: str
    ) -> dict[str, Any] | None:
        prop = self.resolve(path["property"], _PROPERTY_KINDS, cid)
        if prop is None or target is None:
            return None
        if path["inverse"] and prop["kind"] != "OBJECT_PROPERTY":
            self.issue("INVERSE_DATA_PATH", cid)
        scope = (
            prop.get("owner_iri")
            if prop["kind"] == "DATA_PROPERTY"
            else prop.get("range_iri" if path["inverse"] else "domain_iri")
        )
        if not isinstance(scope, str):
            self.issue("MISSING_PROPERTY_CONTEXT", cid, not_run=True)
        elif not self._is_subclass(target["iri"], scope):
            self.issue("PATH_TARGET", cid)
        return prop

    def typed_value(self, value: dict[str, Any], cid: str) -> tuple[str, Any] | None:
        datatype, lexical = value["datatype"], value["lexical"]
        parsed: Any = lexical
        valid = True
        if datatype == "integer":
            valid = bool(re.fullmatch(r"[+-]?[0-9]+", lexical))
            if valid:
                parsed = int(lexical)
        elif datatype == "decimal":
            valid = bool(
                re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", lexical)
            )
            if valid:
                parsed = Decimal(lexical)
        elif datatype == "boolean":
            valid = lexical in {"true", "false", "1", "0"}
            parsed = lexical in {"true", "1"}
        elif datatype == "date":
            try:
                valid = bool(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", lexical))
                date.fromisoformat(lexical)
            except ValueError:
                valid = False
        elif datatype == "anyURI":
            valid = _absolute_iri(lexical)
        if not valid:
            self.issue("INVALID_LEXICAL_VALUE", cid, datatype=datatype)
            return None
        return datatype, parsed

    def pattern(self, spec: dict[str, Any], cid: str) -> None:
        regex = spec["regex"]
        try:
            re.compile(regex)
        except (re.error, OverflowError):
            self.issue("INVALID_PATTERN", cid)
            return
        # Deliberately narrow interoperable subset; never execute the expression.
        escaped = re.sub(r"\\[dDsSwW.^$*+?{}\[\]\\-]", "x", regex)
        outside_classes = re.sub(r"\[[^\]]*\]", "x", escaped)
        repetitions = re.findall(r"[*+?]|\{[0-9]+(?:,[0-9]*)?\}", outside_classes)
        variable_repetitions = [
            token for token in repetitions if token in {"*", "+", "?"} or "," in token
        ]
        if (
            len(regex) > 200
            or not regex.startswith("^")
            or not regex.endswith("$")
            or re.search(r"[()|\\]", escaped)
            or len(variable_repetitions) > 1
            or any(
                int(n) > 1000
                for n in re.findall(r"\d+", "".join(re.findall(r"\{[^}]*\}", regex)))
            )
        ):
            self.issue(
                "UNSUPPORTED",
                cid,
                not_run=True,
                construct="PATTERN_OUTSIDE_SAFE_SUBSET",
            )

    def compile_constraints(self) -> None:
        seen: dict[str, str] = {}
        cardinalities: dict[tuple[str, str, bool], tuple[int, int | None]] = {}
        numeric_intervals: dict[
            tuple[str, str, bool], tuple[Decimal | None, bool, Decimal | None, bool]
        ] = {}
        for item in sorted(
            self.candidate.constraints, key=lambda item: item.candidate_id
        ):
            cid, spec = item.candidate_id, item.spec.model_dump(by_alias=True)
            target = self.resolve(item.target_class.model_dump(), {"CLASS"}, cid)
            if spec["kind"] in _UNSUPPORTED:
                self.issue("UNSUPPORTED", cid, not_run=True, construct=spec["kind"])
                for value in (spec.get("equals"),):
                    if value is not None:
                        self.typed_value(value, cid)
                continue
            prop = self.path(spec["path"], target, cid)
            if prop is None or target is None:
                continue
            kind = spec["kind"]
            if kind in {"NUMERIC_RANGE", "PATTERN", "ENUM"}:
                if prop["kind"] != "DATA_PROPERTY":
                    self.issue(
                        "REFERENCE_KIND",
                        cid,
                        expected=["DATA_PROPERTY"],
                        actual=prop["kind"],
                    )
                if "datatype" not in prop:
                    self.issue(
                        "MISSING_PROPERTY_CONTEXT", cid, not_run=True, field="datatype"
                    )
            if kind == "CARDINALITY":
                minimum, maximum = spec["min"], spec["max"]
                if maximum is not None and minimum > maximum:
                    self.issue("CARDINALITY_RANGE", cid)
                key = target["iri"], prop["iri"], spec["path"]["inverse"]
                previous = cardinalities.get(key, (0, None))
                lower = max(previous[0], minimum)
                upper_values = [v for v in (previous[1], maximum) if v is not None]
                upper = min(upper_values) if upper_values else None
                if upper is not None and lower > upper:
                    self.issue("CARDINALITY_CONFLICT", cid)
                cardinalities[key] = lower, upper
                feature = (
                    "inverse_functional" if spec["path"]["inverse"] else "functional"
                )
                if lower > 1 and prop.get("features", {}).get(feature):
                    self.issue("CARDINALITY_FEATURE_CONFLICT", cid)
            elif kind == "NUMERIC_RANGE":
                if prop.get("datatype") not in {"integer", "decimal"}:
                    self.issue(
                        "DATATYPE_MISMATCH", cid, expected=["integer", "decimal"]
                    )
                lower = (
                    Decimal(spec["minimum"]) if spec["minimum"] is not None else None
                )
                upper = (
                    Decimal(spec["maximum"]) if spec["maximum"] is not None else None
                )
                if lower is None and upper is None:
                    self.issue("EMPTY_NUMERIC_RANGE", cid)
                elif (
                    lower is not None
                    and upper is not None
                    and (
                        lower > upper
                        or (
                            lower == upper
                            and not (
                                spec["minimum_inclusive"] and spec["maximum_inclusive"]
                            )
                        )
                    )
                ):
                    self.issue("NUMERIC_RANGE", cid)
                key = target["iri"], prop["iri"], spec["path"]["inverse"]
                old = numeric_intervals.get(key, (None, True, None, True))
                lower_bounds = [
                    (v, inclusive)
                    for v, inclusive in (
                        (old[0], old[1]),
                        (lower, spec["minimum_inclusive"]),
                    )
                    if v is not None
                ]
                upper_bounds = [
                    (v, inclusive)
                    for v, inclusive in (
                        (old[2], old[3]),
                        (upper, spec["maximum_inclusive"]),
                    )
                    if v is not None
                ]
                lower = max((v for v, _ in lower_bounds), default=None)
                upper = min((v for v, _ in upper_bounds), default=None)
                lower_inclusive = all(flag for v, flag in lower_bounds if v == lower)
                upper_inclusive = all(flag for v, flag in upper_bounds if v == upper)
                numeric_intervals[key] = lower, lower_inclusive, upper, upper_inclusive
                if lower is not None and upper is not None:
                    if lower > upper or (
                        lower == upper and not (lower_inclusive and upper_inclusive)
                    ):
                        self.issue("NUMERIC_RANGE_CONFLICT", cid)
                    if prop.get("datatype") == "integer":
                        first = int(lower.to_integral_value(rounding=ROUND_CEILING))
                        last = int(upper.to_integral_value(rounding=ROUND_FLOOR))
                        first += int(first == lower and not lower_inclusive)
                        last -= int(last == upper and not upper_inclusive)
                        if first > last:
                            self.issue("NUMERIC_RANGE_CONFLICT", cid)
            elif kind == "PATTERN":
                if prop.get("datatype") != "string":
                    self.issue("DATATYPE_MISMATCH", cid, expected=["string"])
                self.pattern(spec, cid)
            elif kind == "ENUM":
                values: set[tuple[str, Any]] = set()
                for value in spec["allowed"]:
                    typed = self.typed_value(value, cid)
                    if value["datatype"] != prop.get("datatype"):
                        self.issue(
                            "DATATYPE_MISMATCH", cid, expected=[prop.get("datatype")]
                        )
                    if typed is not None and typed in values:
                        self.issue("DUPLICATE_ENUM_VALUE", cid)
                    if typed is not None:
                        values.add(typed)
            elif kind == "CLASS_MEMBERSHIP":
                if prop["kind"] != "OBJECT_PROPERTY":
                    self.issue(
                        "REFERENCE_KIND",
                        cid,
                        expected=["OBJECT_PROPERTY"],
                        actual=prop["kind"],
                    )
                classes = self.class_expression(spec["allowed_class"], cid)
                spec["allowed_class"] = {"mode": "ONE", "iris": classes}
            compiled_spec = {
                **spec,
                "path": {"iri": prop["iri"], "inverse": spec["path"]["inverse"]},
            }
            constraint_key = _json({"target_iri": target["iri"], "spec": compiled_spec})
            if constraint_key in seen:
                self.issue("DUPLICATE_CONSTRAINT", cid, other=seen[constraint_key])
            seen[constraint_key] = cid
            self.constraints.append(
                {
                    "candidate_id": cid,
                    "target_iri": target["iri"],
                    "severity": item.severity,
                    "spec": compiled_spec,
                }
            )

    def compile_axioms(self) -> None:
        """Compile only named-class and same-kind property ASTs, not full DL.

        Subproperty cycles are legal OWL and do not create allocation cycles.
        Tautological self-subproperty proposals and exact duplicate declarations
        are rejected explicitly. Equivalence/disjoint conflict checking is only
        over declared named-class equivalences, not a satisfiability proof.
        """
        seen: dict[str, str] = {}
        groups: dict[str, str] = {}

        def root(iri: str) -> str:
            while iri in groups:
                iri = groups[iri]
            return iri

        for item in sorted(self.candidate.axioms, key=lambda item: item.candidate_id):
            cid, spec = item.candidate_id, item.spec.model_dump(by_alias=True)
            kind = spec["kind"]
            operation: dict[str, Any] = {"candidate_id": cid, "kind": kind}
            if kind in {"EQUIVALENT_CLASSES", "DISJOINT_CLASSES"}:
                classes = [self.resolve(ref, {"CLASS"}, cid) for ref in spec["classes"]]
                if any(value is None for value in classes):
                    continue
                iris = [value["iri"] for value in classes if value is not None]
                if len(set(iris)) != len(iris):
                    self.issue("DUPLICATE_REFERENCE", cid)
                    continue
                operation["iris"] = sorted(iris)
                if kind == "EQUIVALENT_CLASSES":
                    for iri in iris[1:]:
                        left, right = root(iris[0]), root(iri)
                        if left != right:
                            groups[max(left, right)] = min(left, right)
            elif kind == "SUBPROPERTY":
                sub = self.resolve(spec["sub"], _PROPERTY_KINDS, cid)
                super_ = self.resolve(spec["super"], _PROPERTY_KINDS, cid)
                if sub is None or super_ is None:
                    continue
                if sub["kind"] != super_["kind"]:
                    self.issue(
                        "REFERENCE_KIND",
                        cid,
                        expected=[sub["kind"]],
                        actual=super_["kind"],
                    )
                    continue
                if sub["iri"] == super_["iri"]:
                    self.issue("INVALID_AXIOM", cid, reason="self_subproperty")
                    continue
                operation.update(sub_iri=sub["iri"], super_iri=super_["iri"])
            else:
                self.issue("UNSUPPORTED", cid, not_run=True, construct=kind)
                continue
            identity = _json(
                {
                    key: value
                    for key, value in operation.items()
                    if key != "candidate_id"
                }
            )
            if identity in seen:
                self.issue("DUPLICATE_AXIOM", cid, other=seen[identity])
            seen[identity] = cid
            self.axioms.append(operation)
        for operation in self.axioms:
            if operation["kind"] == "DISJOINT_CLASSES":
                roots = [root(iri) for iri in operation["iris"]]
                if len(set(roots)) != len(roots):
                    self.issue(
                        "AXIOM_CONFLICT",
                        operation["candidate_id"],
                        reason="equivalent_disjoint_classes",
                    )

    def order(self) -> list[str]:
        pending = {cid: set(deps) for cid, deps in self.dependencies.items()}
        result: list[str] = []
        while pending:
            ready = sorted(cid for cid, deps in pending.items() if not deps)
            if not ready:
                self.issue("DEPENDENCY_CYCLE", candidates=sorted(pending))
                return result
            for cid in ready:
                result.append(cid)
                del pending[cid]
            for deps in pending.values():
                deps.difference_update(ready)
        return result


def compile_candidate(
    candidate: OntologyCandidate,
    *,
    namespace_catalog: Mapping[str, Mapping[str, object]],
    asset_catalog: Mapping[str, Mapping[str, object]],
    source_catalog: Mapping[str, Mapping[str, str]],
    context_token: str,
    profile: str = "BUSINESS",
) -> dict[str, Any]:
    """Compile a validated AST against authoritative JSON catalogs, fail closed.

    Asset optional fields: metadata (candidate-style), owner_iri, datatype,
    domain_iri, range_iri, inverse_iri, features and parents (IRI list). No field
    from a REUSE candidate can update these. Missing scope information blocks
    operations requiring it. source_catalog holds nonempty server-located spans;
    supplied text proves only a reference exists, not that a claim follows it.
    """
    # Revalidate even model_construct/mutated nested instances at this boundary.
    candidate = parse_candidate_json(
        _json(candidate.model_dump(by_alias=True, warnings=False))
    )
    compiler = _Compiler(candidate, namespace_catalog, asset_catalog, source_catalog)
    if candidate.context_token != context_token:
        compiler.issue("CONTEXT_MISMATCH")
    if candidate.profile_echo != profile or profile not in {
        "BUSINESS",
        "STANDARD_DIGITALIZATION",
    }:
        compiler.issue("PROFILE_MISMATCH")
    if profile == "STANDARD_DIGITALIZATION":
        compiler.issue(
            "UNSUPPORTED", not_run=True, construct="STANDARD_DIGITALIZATION_PROFILE"
        )
    compiler.prepare()
    compiler.resource_details()
    compiler.compile_axioms()
    compiler.compile_constraints()
    order = compiler.order()
    issues = sorted(
        {_json(issue): issue for issue in compiler.issues}.values(), key=_json
    )
    blocked = any(issue["blocking"] for issue in issues)
    canonical = candidate.model_dump(by_alias=True)
    for field in ("resources", "constraints", "axioms"):
        canonical[field].sort(key=lambda item: item["candidate_id"])
    canonical["questions"].sort(key=lambda item: item["id"])
    plan = {
        "compiler_version": COMPILER_VERSION,
        "state": "BLOCKED" if blocked else "COMPILED",
        "canonical_candidate": canonical,
        "resources": []
        if blocked
        else [compiler.operations[cid] for cid in order if cid in compiler.operations],
        "constraints": [] if blocked else compiler.constraints,
        "axioms": [] if blocked else compiler.axioms,
        "metadata": None
        if blocked or candidate.ontology_metadata is None
        else candidate.ontology_metadata.metadata.model_dump(by_alias=True),
        "dependencies": {
            cid: sorted(deps) for cid, deps in sorted(compiler.dependencies.items())
        },
        "inverse_links": []
        if blocked
        else [
            {"left_iri": left, "right_iri": right}
            for left, right in sorted(compiler.inverse_links)
        ],
        "issues": issues,
    }
    try:
        plan["digest"] = _digest(
            {
                "plan": plan,
                "context_token": context_token,
                "profile": profile,
                "namespace_catalog": {
                    key: dict(value) for key, value in namespace_catalog.items()
                },
                "asset_catalog": {
                    key: dict(value) for key, value in asset_catalog.items()
                },
                "source_catalog": {
                    key: dict(value) for key, value in source_catalog.items()
                },
            }
        )
    except (ValueError, TypeError, UnicodeError) as exc:
        raise CandidateParseError("KG.CANDIDATE_INVALID_CATALOG_JSON") from exc
    return plan
