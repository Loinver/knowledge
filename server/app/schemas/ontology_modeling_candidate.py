"""Strict, offline ontology-candidate/1.0 transport, separate from legacy arrays.

Use parse_candidate_json at the untrusted JSON boundary: Pydantic alone cannot
detect duplicate JSON keys. Recognized future constructs remain in the AST so
the compiler can explicitly report NOT_RUN instead of dropping them.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_core import PydanticCustomError

MAX_CANDIDATE_BYTES = 262_144
MAX_CANDIDATE_DEPTH = 24
MAX_CANDIDATE_NODES = 20_000


class CandidateErrorCode(StrEnum):
    """Complete compiler/parser code catalog for application mapping and i18n."""

    AXIOM_CONFLICT = "KG.CANDIDATE_AXIOM_CONFLICT"
    CARDINALITY_CONFLICT = "KG.CANDIDATE_CARDINALITY_CONFLICT"
    CARDINALITY_FEATURE_CONFLICT = "KG.CANDIDATE_CARDINALITY_FEATURE_CONFLICT"
    CARDINALITY_RANGE = "KG.CANDIDATE_CARDINALITY_RANGE"
    CONTEXT_MISMATCH = "KG.CANDIDATE_CONTEXT_MISMATCH"
    DATATYPE_MISMATCH = "KG.CANDIDATE_DATATYPE_MISMATCH"
    DEPENDENCY_CYCLE = "KG.CANDIDATE_DEPENDENCY_CYCLE"
    DUPLICATE_AXIOM = "KG.CANDIDATE_DUPLICATE_AXIOM"
    DUPLICATE_CONSTRAINT = "KG.CANDIDATE_DUPLICATE_CONSTRAINT"
    DUPLICATE_ENUM_VALUE = "KG.CANDIDATE_DUPLICATE_ENUM_VALUE"
    DUPLICATE_EVIDENCE_REFERENCE = "KG.CANDIDATE_DUPLICATE_EVIDENCE_REFERENCE"
    DUPLICATE_ID = "KG.CANDIDATE_DUPLICATE_ID"
    DUPLICATE_JSON_KEY = "KG.CANDIDATE_DUPLICATE_JSON_KEY"
    DUPLICATE_QUESTION = "KG.CANDIDATE_DUPLICATE_QUESTION"
    DUPLICATE_REFERENCE = "KG.CANDIDATE_DUPLICATE_REFERENCE"
    DUPLICATE_RESOURCE = "KG.CANDIDATE_DUPLICATE_RESOURCE"
    EMPTY_NUMERIC_RANGE = "KG.CANDIDATE_EMPTY_NUMERIC_RANGE"
    FEATURE_CONFLICT = "KG.CANDIDATE_FEATURE_CONFLICT"
    INHERITANCE_CYCLE = "KG.CANDIDATE_INHERITANCE_CYCLE"
    INVALID_AXIOM = "KG.CANDIDATE_INVALID_AXIOM"
    INVALID_CATALOG = "KG.CANDIDATE_INVALID_CATALOG"
    INVALID_CATALOG_JSON = "KG.CANDIDATE_INVALID_CATALOG_JSON"
    INVALID_JSON = "KG.CANDIDATE_INVALID_JSON"
    INVALID_LEXICAL_VALUE = "KG.CANDIDATE_INVALID_LEXICAL_VALUE"
    INVALID_NAME = "KG.CANDIDATE_INVALID_NAME"
    INVALID_PATTERN = "KG.CANDIDATE_INVALID_PATTERN"
    INVALID_SOURCE = "KG.CANDIDATE_INVALID_SOURCE"
    INVALID_SOURCE_SPAN = "KG.CANDIDATE_INVALID_SOURCE_SPAN"
    INVALID_STRUCTURE = "KG.CANDIDATE_INVALID_STRUCTURE"
    INVERSE_CONFLICT = "KG.CANDIDATE_INVERSE_CONFLICT"
    INVERSE_DATA_PATH = "KG.CANDIDATE_INVERSE_DATA_PATH"
    INVERSE_ENDPOINTS = "KG.CANDIDATE_INVERSE_ENDPOINTS"
    MISSING_PROPERTY_CONTEXT = "KG.CANDIDATE_MISSING_PROPERTY_CONTEXT"
    NEW_REQUIRES_REUSE = "KG.CANDIDATE_NEW_REQUIRES_REUSE"
    NUMERIC_RANGE = "KG.CANDIDATE_NUMERIC_RANGE"
    NUMERIC_RANGE_CONFLICT = "KG.CANDIDATE_NUMERIC_RANGE_CONFLICT"
    OWNER_NAMESPACE = "KG.CANDIDATE_OWNER_NAMESPACE"
    PATH_TARGET = "KG.CANDIDATE_PATH_TARGET"
    POSSIBLE_SYNONYM = "KG.CANDIDATE_POSSIBLE_SYNONYM"
    PROFILE_MISMATCH = "KG.CANDIDATE_PROFILE_MISMATCH"
    PROTECTED_NAMESPACE = "KG.CANDIDATE_PROTECTED_NAMESPACE"
    QUESTION_ASSOCIATION = "KG.CANDIDATE_QUESTION_ASSOCIATION"
    REFERENCE_KIND = "KG.CANDIDATE_REFERENCE_KIND"
    TOO_COMPLEX = "KG.CANDIDATE_TOO_COMPLEX"
    TOO_LARGE = "KG.CANDIDATE_TOO_LARGE"
    UNKNOWN_DEPENDENCY = "KG.CANDIDATE_UNKNOWN_DEPENDENCY"
    UNKNOWN_NAMESPACE = "KG.CANDIDATE_UNKNOWN_NAMESPACE"
    UNKNOWN_QUESTION = "KG.CANDIDATE_UNKNOWN_QUESTION"
    UNKNOWN_QUESTION_CANDIDATE = "KG.CANDIDATE_UNKNOWN_QUESTION_CANDIDATE"
    UNKNOWN_REFERENCE = "KG.CANDIDATE_UNKNOWN_REFERENCE"
    UNKNOWN_SOURCE_SPAN = "KG.CANDIDATE_UNKNOWN_SOURCE_SPAN"
    UNRESOLVED_QUESTION = "KG.CANDIDATE_UNRESOLVED_QUESTION"
    UNRESOLVED_UNCERTAINTY = "KG.CANDIDATE_UNRESOLVED_UNCERTAINTY"
    UNSUPPORTED = "KG.CANDIDATE_UNSUPPORTED"


CandidateId = Annotated[str, Field(pattern=r"^c:[A-Za-z][A-Za-z0-9_-]{0,63}$")]
Handle = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9:_-]{0,127}$")]
LocalName = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,127}$")]
Text = Annotated[str, Field(min_length=1, max_length=4000)]
Label = Annotated[str, Field(min_length=1, max_length=200)]
Datatype = Literal["string", "integer", "decimal", "boolean", "date", "anyURI"]
AssetKind = Literal["CLASS", "DATA_PROPERTY", "OBJECT_PROPERTY"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class LocalizedText(StrictModel):
    zh_cn: Text | None = Field(alias="zh-CN")
    en_us: Text | None = Field(alias="en-US")

    @model_validator(mode="after")
    def reject_blank(self) -> Self:
        if any(v is not None and not v.strip() for v in (self.zh_cn, self.en_us)):
            raise PydanticCustomError("blank_text", "blank_text")
        return self


class NonEmptyLocalizedText(LocalizedText):
    @model_validator(mode="after")
    def require_text(self) -> Self:
        if self.zh_cn is None and self.en_us is None:
            raise PydanticCustomError("empty_text", "empty_text")
        return self


class Labels(StrictModel):
    zh_cn: Label = Field(alias="zh-CN")
    en_us: Label | None = Field(alias="en-US")

    @model_validator(mode="after")
    def reject_blank(self) -> Self:
        if not self.zh_cn.strip() or (
            self.en_us is not None and not self.en_us.strip()
        ):
            raise PydanticCustomError("blank_label", "blank_label")
        return self


class CandidateRef(StrictModel):
    kind: Literal["CANDIDATE"]
    candidate_id: CandidateId


class CatalogRef(StrictModel):
    kind: Literal["CATALOG"]
    handle: Handle


Ref = Annotated[CandidateRef | CatalogRef, Field(discriminator="kind")]


class SourceRef(StrictModel):
    source_handle: Handle
    span_handle: Handle


class Synonym(StrictModel):
    language: Literal["zh-CN", "en-US"]
    text: Label

    @model_validator(mode="after")
    def reject_blank(self) -> Self:
        if not self.text.strip():
            raise PydanticCustomError("blank_text", "blank_text")
        return self


class Evidence(StrictModel):
    basis: Literal["SOURCE", "ASSET", "PROPOSAL"]
    source_refs: Annotated[list[SourceRef], Field(max_length=20)]
    rationale_i18n: NonEmptyLocalizedText
    depends_on: Annotated[list[CandidateId], Field(max_length=100)]
    uncertainty_ids: Annotated[list[Handle], Field(max_length=30)]

    @model_validator(mode="after")
    def require_source(self) -> Self:
        if self.basis != "PROPOSAL" and not self.source_refs:
            raise PydanticCustomError("missing_source", "missing_source")
        return self


class Metadata(StrictModel):
    labels: Labels
    definitions: LocalizedText
    synonyms: Annotated[list[Synonym], Field(max_length=30)]


class ClassExpression(StrictModel):
    mode: Literal["ONE", "ANY_OF", "ALL_OF"]
    refs: Annotated[list[Ref], Field(min_length=1, max_length=20)]

    @model_validator(mode="after")
    def check_count(self) -> Self:
        if (self.mode == "ONE" and len(self.refs) != 1) or (
            self.mode != "ONE" and len(self.refs) < 2
        ):
            raise PydanticCustomError("expression_arity", "expression_arity")
        return self


class Features(StrictModel):
    functional: bool
    inverse_functional: bool
    symmetric: bool
    transitive: bool
    asymmetric: bool
    reflexive: bool
    irreflexive: bool


class TypedValue(StrictModel):
    datatype: Datatype
    lexical: Annotated[str, Field(min_length=1, max_length=1000)]


class Question(StrictModel):
    id: Handle
    question_i18n: NonEmptyLocalizedText
    blocking: bool
    related_candidate_ids: Annotated[list[CandidateId], Field(max_length=100)]


class NewClass(StrictModel):
    kind: Literal["NEW_CLASS"]
    namespace_handle: Handle
    local_name: LocalName
    metadata: Metadata
    parents: Annotated[list[Ref], Field(max_length=20)]


class NewDataProperty(StrictModel):
    kind: Literal["NEW_DATA_PROPERTY"]
    namespace_handle: Handle
    local_name: LocalName
    metadata: Metadata
    owner: Ref
    datatype: Datatype


class NewObjectProperty(StrictModel):
    kind: Literal["NEW_OBJECT_PROPERTY"]
    namespace_handle: Handle
    local_name: LocalName
    metadata: Metadata
    domain: ClassExpression
    range: ClassExpression
    inverse_of: Ref | None
    features: Features


class Reuse(StrictModel):
    kind: Literal["REUSE"]
    handle: Handle
    expected_kind: AssetKind
    attach_to_ontology: bool


ResourceSpec = Annotated[
    NewClass | NewDataProperty | NewObjectProperty | Reuse,
    Field(discriminator="kind"),
]


class ResourceCandidate(StrictModel):
    candidate_id: CandidateId
    spec: ResourceSpec
    evidence: Evidence


class ClassAxiom(StrictModel):
    kind: Literal["EQUIVALENT_CLASSES", "DISJOINT_CLASSES"]
    classes: Annotated[list[Ref], Field(min_length=2, max_length=20)]


class HasKey(StrictModel):
    kind: Literal["HAS_KEY"]
    class_ref: Ref = Field(alias="class")
    properties: Annotated[list[Ref], Field(min_length=1, max_length=20)]


class Subproperty(StrictModel):
    kind: Literal["SUBPROPERTY"]
    sub: Ref
    super_ref: Ref = Field(alias="super")


class PropertyChain(StrictModel):
    kind: Literal["PROPERTY_CHAIN"]
    chain: Annotated[list[Ref], Field(min_length=2, max_length=10)]
    super_ref: Ref = Field(alias="super")


AxiomSpec = Annotated[
    ClassAxiom | HasKey | Subproperty | PropertyChain, Field(discriminator="kind")
]


class AxiomCandidate(StrictModel):
    candidate_id: CandidateId
    spec: AxiomSpec
    evidence: Evidence


class PropertyPath(StrictModel):
    property: Ref
    inverse: bool


class Cardinality(StrictModel):
    kind: Literal["CARDINALITY"]
    path: PropertyPath
    min: Annotated[int, Field(ge=0)]
    max: Annotated[int, Field(ge=0)] | None


class Enumeration(StrictModel):
    kind: Literal["ENUM"]
    path: PropertyPath
    allowed: Annotated[list[TypedValue], Field(min_length=1, max_length=100)]


class Pattern(StrictModel):
    kind: Literal["PATTERN"]
    path: PropertyPath
    regex: Annotated[str, Field(min_length=1, max_length=500)]
    flags: Literal["", "i", "m", "im"]


DecimalText = Annotated[str, Field(pattern=r"^-?[0-9]+(\.[0-9]+)?$", max_length=1000)]


class NumericRange(StrictModel):
    kind: Literal["NUMERIC_RANGE"]
    path: PropertyPath
    minimum: DecimalText | None
    maximum: DecimalText | None
    minimum_inclusive: bool
    maximum_inclusive: bool


class DateOrder(StrictModel):
    kind: Literal["DATE_ORDER"]
    earlier: PropertyPath
    later: PropertyPath
    allow_equal: bool


class UniqueTuple(StrictModel):
    kind: Literal["UNIQUE_TUPLE"]
    paths: Annotated[list[PropertyPath], Field(min_length=1, max_length=10)]
    scope: Literal["VALIDATION_DATASET"]


class ClassMembership(StrictModel):
    kind: Literal["CLASS_MEMBERSHIP"]
    path: PropertyPath
    allowed_class: ClassExpression


class ConditionalRequired(StrictModel):
    kind: Literal["CONDITIONAL_REQUIRED"]
    when_path: PropertyPath
    equals: TypedValue
    require_any: Annotated[list[PropertyPath], Field(min_length=1, max_length=10)]


ConstraintSpec = Annotated[
    Cardinality
    | Enumeration
    | Pattern
    | NumericRange
    | DateOrder
    | UniqueTuple
    | ClassMembership
    | ConditionalRequired,
    Field(discriminator="kind"),
]


class ConstraintCandidate(StrictModel):
    candidate_id: CandidateId
    target_class: Ref
    spec: ConstraintSpec
    severity: Literal["INFO", "WARNING", "VIOLATION"]
    evidence: Evidence


class Scope(StrictModel):
    goal_i18n: NonEmptyLocalizedText
    out_of_scope_i18n: Annotated[list[LocalizedText], Field(max_length=20)]
    assumptions_i18n: Annotated[list[LocalizedText], Field(max_length=30)]


class OntologyMetadata(StrictModel):
    metadata: Metadata
    evidence: Evidence


class OntologyCandidate(StrictModel):
    model_config = ConfigDict(
        json_schema_extra={
            "$id": "urn:knowledge:proposal:ontology-candidate:1.0",
            "$schema": "https://json-schema.org/draft/2020-12/schema",
        }
    )

    schema_version: Literal["ontology-candidate/1.0"]
    context_token: Annotated[str, Field(min_length=1, max_length=256)]
    profile_echo: Literal["BUSINESS", "STANDARD_DIGITALIZATION"]
    scope: Scope
    ontology_metadata: OntologyMetadata | None
    resources: Annotated[list[ResourceCandidate], Field(max_length=200)]
    axioms: Annotated[list[AxiomCandidate], Field(max_length=100)]
    constraints: Annotated[list[ConstraintCandidate], Field(max_length=200)]
    questions: Annotated[list[Question], Field(max_length=50)]


class CandidateParseError(ValueError):
    """Safe boundary failure: codes/locations only, never echo source input."""

    def __init__(self, code: str, params: dict[str, Any] | None = None) -> None:
        self.code = CandidateErrorCode(code).value
        self.params = params or {}
        super().__init__(code)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CandidateParseError("KG.CANDIDATE_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise CandidateParseError("KG.CANDIDATE_INVALID_JSON")


def parse_bounded_json(
    raw: str | bytes, *, max_bytes: int = MAX_CANDIDATE_BYTES
) -> Any:
    if not isinstance(raw, (str, bytes)):
        raise CandidateParseError("KG.CANDIDATE_INVALID_JSON")
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if len(encoded) > max_bytes:
            raise CandidateParseError("KG.CANDIDATE_TOO_LARGE")
        value = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        pending = [(value, 1)]
        nodes = 0
        while pending:
            node, depth = pending.pop()
            nodes += 1
            if depth > MAX_CANDIDATE_DEPTH or nodes > MAX_CANDIDATE_NODES:
                raise CandidateParseError("KG.CANDIDATE_TOO_COMPLEX")
            if isinstance(node, dict):
                pending.extend((v, depth + 1) for v in node.values())
            elif isinstance(node, list):
                pending.extend((v, depth + 1) for v in node)
        return value
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, CandidateParseError):
            raise
        raise CandidateParseError("KG.CANDIDATE_INVALID_JSON") from exc


def parse_candidate_json(raw: str | bytes) -> OntologyCandidate:
    try:
        return OntologyCandidate.model_validate(parse_bounded_json(raw))
    except ValidationError as exc:
        raise CandidateParseError(
            "KG.CANDIDATE_INVALID_STRUCTURE",
            {
                "errors": [
                    {"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors()
                ]
            },
        ) from exc
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, CandidateParseError):
            raise
        raise CandidateParseError("KG.CANDIDATE_INVALID_JSON") from exc
