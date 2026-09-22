"""版本化枚举字典的传输契约。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import ResourceKind, ResourceStatus

EnumDictionarySort = Literal["name", "-name", "id", "-id"]


def validate_labels(value: dict[str, str]) -> dict[str, str]:
    labels = {key: text.strip() for key, text in value.items()}
    if not labels.get("zh-CN") or set(labels) - {"zh-CN", "en-US"}:
        raise ValueError("zh-CN is required; only zh-CN and en-US are supported")
    if any(len(text) > 4096 for text in labels.values()):
        raise ValueError("labels must not exceed 4096 characters")
    return labels


class EnumEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    value: str = Field(min_length=1, max_length=256)
    label_i18n: dict[str, str]

    _labels = field_validator("label_i18n")(validate_labels)


class EnumDictionaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Z][A-Za-z0-9]*$")
    label_i18n: dict[str, str]
    definition_i18n: dict[str, str]
    entries: list[EnumEntry] = Field(min_length=1, max_length=1000)

    _labels = field_validator("label_i18n", "definition_i18n")(validate_labels)

    @model_validator(mode="after")
    def unique_values(self) -> EnumDictionaryInput:
        if len({entry.value for entry in self.entries}) != len(self.entries):
            raise ValueError("entry values must be unique")
        return self


class EnumDictionaryOut(EnumDictionaryInput):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    revision: int


class EnumDictionaryPage(BaseModel):
    items: list[EnumDictionaryOut]
    total: int
    page: int
    page_size: int


class EnumReferenceOut(BaseModel):
    resource_id: int
    resource_name: str
    resource_kind: ResourceKind
    resource_status: ResourceStatus
    property_id: int
    property_name: str
    enum_dict_revision: int
    latest_revision: int
