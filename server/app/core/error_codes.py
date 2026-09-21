"""错误码注册表（H-01 统一 API 契约）。

后端只返回错误码 + 结构化参数，绝不返回面向用户的中文句子。
前端按 code 查 i18n 表渲染。HTTP 状态码表达大类，code 表达具体原因。
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """错误码枚举。值即对外传输的字符串。"""

    # 400 请求本身不合法
    INVALID_IRI = "KG.INVALID_IRI"
    INVALID_NAME = "KG.INVALID_NAME"
    INVALID_NAMESPACE = "KG.INVALID_NAMESPACE"
    INVALID_REQUEST = "KG.INVALID_REQUEST"

    # 404 资源不存在
    RESOURCE_NOT_FOUND = "KG.RESOURCE_NOT_FOUND"
    REVISION_NOT_FOUND = "KG.REVISION_NOT_FOUND"

    # 409 版本/状态冲突
    REVISION_CONFLICT = "KG.REVISION_CONFLICT"
    ALREADY_PUBLISHED = "KG.ALREADY_PUBLISHED"
    PROTECTED_NAMESPACE = "KG.PROTECTED_NAMESPACE"

    # 422 语义校验违反
    VALIDATION_VIOLATION = "KG.VALIDATION_VIOLATION"

    # 503 外部依赖不可用
    SOURCE_UNREACHABLE = "KG.SOURCE_UNREACHABLE"
    REASONER_UNAVAILABLE = "KG.REASONER_UNAVAILABLE"


# 错误码到 HTTP 状态码的映射。新增 code 必须在这里登记。
HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.INVALID_IRI: 400,
    ErrorCode.INVALID_NAME: 400,
    ErrorCode.INVALID_NAMESPACE: 400,
    ErrorCode.INVALID_REQUEST: 400,
    ErrorCode.RESOURCE_NOT_FOUND: 404,
    ErrorCode.REVISION_NOT_FOUND: 404,
    ErrorCode.REVISION_CONFLICT: 409,
    ErrorCode.ALREADY_PUBLISHED: 409,
    ErrorCode.PROTECTED_NAMESPACE: 409,
    ErrorCode.VALIDATION_VIOLATION: 422,
    ErrorCode.SOURCE_UNREACHABLE: 503,
    ErrorCode.REASONER_UNAVAILABLE: 503,
}
