"""元数据采集与目录（H-21）的请求/响应模型。

catalog 结构：schema -> tables -> columns。SQLite 无 schema 概念，统一归 main。
catalog 只存结构，不含数据；凭据不出现在 catalog。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool
    primary_key: bool
    foreign_key: str | None = None  # "ref_table.ref_column"


class TableInfo(BaseModel):
    name: str
    type: str  # table / view
    columns: list[ColumnInfo]


class SchemaInfo(BaseModel):
    db_schema: str = Field(alias="schema")
    tables: list[TableInfo]


class Catalog(BaseModel):
    """采集到的结构快照。"""

    schemas: list[SchemaInfo]
    table_count: int
    column_count: int


class DiffEntry(BaseModel):
    name: str
    type: str  # added / removed / modified
    db_schema: str = Field(alias="schema")
    details: str | None = None


class DiffColumnEntry(BaseModel):
    table: str
    db_schema: str = Field(alias="schema")
    column: str
    type: str  # added / removed / modified
    details: str | None = None


class CatalogDiff(BaseModel):
    tables: list[DiffEntry]
    columns: list[DiffColumnEntry]
    summary: dict[str, int]


class MetadataSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    datasource_id: int
    revision: int
    catalog: dict
    diff: dict | None
    captured_at: datetime


class MetadataSnapshotBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    revision: int
    captured_at: datetime


class ReferenceItem(BaseModel):
    """反向引用：该表被哪些映射引用。"""

    mapping_id: int
    mapping_name: str
    role: str  # entity / relation


class TableReferenceResponse(BaseModel):
    table: str
    references: list[ReferenceItem]
