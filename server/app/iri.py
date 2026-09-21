"""IRI 生成与校验（H-03 命名空间与 IRI 治理的最小核心）。

规则：
- 资源的机读名（name）只能由 ASCII 字母数字组成，且首字母大写；
- IRI = 命名空间前缀 + 机读名，前缀必须以 # 或 / 结尾。
"""

from __future__ import annotations

import re

NAME_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9]*$")
NAMESPACE_PATTERN = re.compile(r"^https?://[^\s<>\"']+[#/]$")


def is_valid_name(name: str) -> bool:
    """判断机读名是否合法（类 PascalCase，无下划线与连字符）。"""
    return bool(NAME_PATTERN.match(name))


def is_valid_namespace(namespace: str) -> bool:
    """判断命名空间前缀是否合法（以 # 或 / 结尾的 http/https 地址）。"""
    return bool(NAMESPACE_PATTERN.match(namespace))


def build_iri(namespace: str, name: str) -> str:
    """拼接命名空间与机读名，得到资源的稳定 IRI。

    Raises:
        ValueError: 命名空间或机读名不合法时抛出，不做静默修正。
    """
    if not is_valid_namespace(namespace):
        raise ValueError(f"非法的命名空间前缀：{namespace!r}")
    if not is_valid_name(name):
        raise ValueError(f"非法的机读名：{name!r}")
    return f"{namespace}{name}"
