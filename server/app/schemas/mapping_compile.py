"""映射编译预览（H-31）的响应模型。

字段四列实算：目标属性 → 源字段 → 转换规则 → 空值策略。
错误定位到字段级（entity/attr 或 relation/endpoint）。
"""

from __future__ import annotations

from pydantic import BaseModel


class CompiledCell(BaseModel):
    """单字段实算结果。"""

    target_attr: str
    source_field: str
    value: object | None
    status: str  # ok / empty / error
    message: str | None = None


class CompiledRow(BaseModel):
    row_index: int
    source_key: str | None  # 源行主键拼接
    cells: list[CompiledCell]


class EntityCompiled(BaseModel):
    entity_type: str
    table: str
    rows: list[CompiledRow]
    errors: list[dict]  # 字段级错误


class RelationCompiled(BaseModel):
    relation_type: str
    mode: str
    table: str
    rows: list[dict]  # 编译后的关系三元组样例
    errors: list[dict]


class MappingPreviewResult(BaseModel):
    """映射编译预览总结果。"""

    mapping_id: int
    revision: int
    onto_version: int
    entities: list[EntityCompiled]
    relations: list[RelationCompiled]
    summary: dict
