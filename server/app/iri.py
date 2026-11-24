"""IRI 生成与校验（H-03 命名空间与 IRI 治理的最小核心）。

规则：
- 资源的机读名（name）只能由 ASCII 字母数字组成，且首字母大写；
- IRI = 命名空间前缀 + 机读名，前缀必须以 # 或 / 结尾。
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

NAME_PATTERN = re.compile(r"^[A-Z][A-Za-z0-9]*$")
NAMESPACE_PATTERN = re.compile(r"^https?://[^\s<>\"']+[#/]$")
PROPERTY_NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9]*")
LEGACY_PROPERTY_NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def is_valid_any_uri(value: str) -> bool:
    """支持绝对/相对 URI 引用；仅检查词法，不解析网络或改写输入。

    空引用合法；拒绝空白、控制字符、非法百分号转义与 URI 禁用字符。
    Unicode 保留原值，调用方需要 URL 编码时自行明确转换。
    """
    if re.search(r'[\s\x00-\x20\x7f<>"{}|\\^`]', value):
        return False
    if re.search(r"%(?![0-9A-Fa-f]{2})", value):
        return False
    try:
        urlsplit(value)
    except ValueError:
        return False
    return True


def is_valid_property_name(name: str, *, allow_legacy_underscore: bool = False) -> bool:
    """属性名允许小写开头；数据属性可兼容既有蛇形字段，不改写 IRI。"""
    pattern = (
        LEGACY_PROPERTY_NAME_PATTERN
        if allow_legacy_underscore
        else PROPERTY_NAME_PATTERN
    )
    return bool(pattern.fullmatch(name))


def build_property_iri(namespace: str, name: str) -> str:
    """按属性命名策略拼接 IRI，类名仍使用 build_iri 的原有规则。"""
    if not is_valid_namespace(namespace):
        raise ValueError("invalid_namespace")
    if not is_valid_property_name(name):
        raise ValueError("invalid_property_name")
    return f"{namespace}{name}"


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
