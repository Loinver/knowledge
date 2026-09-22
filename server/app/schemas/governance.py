"""规则 CRUD 与真实正反例校验契约。"""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.models.enums import ValidationState

RuleSourceKind = Literal["STANDARD", "ENTERPRISE"]
RuleSort = Literal["identifier", "-identifier", "id", "-id"]


class RuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    identifier: str = Field(min_length=1, max_length=128)
    name_i18n: dict[str, str]
    category: str = Field(min_length=1, max_length=128)
    source_kind: RuleSourceKind
    source_reference: str = Field(min_length=1, max_length=512)
    target_iri: str = Field(min_length=1, max_length=2048)
    severity: Literal["INFO", "WARNING", "VIOLATION"]
    language: Literal["SHACL", "OWL"]
    expression: str = Field(min_length=1, max_length=65536)
    execution: Literal["AUTO", "MANUAL"]
    positive_example: str = Field(min_length=1, max_length=65536)
    negative_example: str = Field(min_length=1, max_length=65536)

    @field_validator("name_i18n")
    @classmethod
    def validate_name(cls, value: dict[str, str]) -> dict[str, str]:
        if (
            not value.get("zh-CN", "").strip()
            or set(value) - {"zh-CN", "en-US"}
            or any(not text.strip() or len(text) > 256 for text in value.values())
        ):
            raise KGError(ErrorCode.INVALID_NAME, {"field": "name_i18n"})
        return {locale: text.strip() for locale, text in value.items()}

    @field_validator("target_iri")
    @classmethod
    def validate_target_iri(cls, value: str) -> str:
        try:
            parts = urlsplit(value)
            valid = bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:.+", value))
            valid = valid and not any(
                char.isspace() or ord(char) < 32 or char in '<>"{}|^`\\'
                for char in value
            )
            if parts.scheme in {"http", "https"}:
                valid = valid and bool(parts.hostname)
        except ValueError:
            valid = False
        if not valid:
            raise KGError(ErrorCode.INVALID_IRI, {"field": "target_iri"})
        return value


class RuleOut(RuleCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    revision: int


class RulePage(BaseModel):
    items: list[RuleOut]
    total: int
    page: int
    page_size: int


class RuleExampleOut(BaseModel):
    state: ValidationState
    conforms: bool
    report_text: str


class RuleTestOut(BaseModel):
    rule_id: int
    revision: int
    state: ValidationState
    positive: RuleExampleOut | None = None
    negative: RuleExampleOut | None = None


ClauseAppendixNature = Literal["NORMATIVE", "INFORMATIVE"]
ClauseSort = Literal[
    "standard",
    "-standard",
    "clause_number",
    "-clause_number",
    "id",
    "-id",
]


class StandardClauseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    standard: str = Field(min_length=1, max_length=64)
    clause_number: str = Field(min_length=1, max_length=32)
    title_i18n: dict[str, str]
    self_authored_description: dict[str, str]
    product_fallback: str | None = Field(default=None, max_length=256)
    appendix_nature: ClauseAppendixNature = "NORMATIVE"
    date_lexicon: str | None = Field(default=None, max_length=128)
    clause_disambiguation: str | None = Field(default=None, max_length=512)
    example_domain: str | None = Field(default=None, max_length=128)

    @field_validator("title_i18n", "self_authored_description")
    @classmethod
    def _require_zh_cn(cls, value: dict[str, str]) -> dict[str, str]:
        if not value.get("zh-CN", "").strip():
            raise ValueError("zh-CN is required")
        if set(value) - {"zh-CN", "en-US"}:
            raise ValueError("only zh-CN and en-US are allowed")
        return value


class StandardClauseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title_i18n: dict[str, str] | None = None
    self_authored_description: dict[str, str] | None = None
    product_fallback: str | None = None
    appendix_nature: ClauseAppendixNature | None = None
    date_lexicon: str | None = None
    clause_disambiguation: str | None = None
    example_domain: str | None = None


class StandardClauseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    revision: int
    standard: str
    clause_number: str
    title_i18n: dict[str, str]
    self_authored_description: dict[str, str]
    product_fallback: str | None
    appendix_nature: str
    date_lexicon: str | None
    clause_disambiguation: str | None
    example_domain: str | None


class StandardClauseBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    standard: str
    clause_number: str
    product_fallback: str | None


class StandardClausePage(BaseModel):
    items: list[StandardClauseBrief]
    total: int
    page: int
    page_size: int
