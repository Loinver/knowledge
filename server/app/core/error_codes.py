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
    ALREADY_EXISTS = "KG.ALREADY_EXISTS"

    # 422 语义校验违反
    VALIDATION_VIOLATION = "KG.VALIDATION_VIOLATION"

    # 503 外部依赖不可用
    SOURCE_UNREACHABLE = "KG.SOURCE_UNREACHABLE"
    REASONER_UNAVAILABLE = "KG.REASONER_UNAVAILABLE"

    # 503 元数据库异常。最常见的成因是本地库结构落后于代码（没跑迁移），
    # 表现为查询报 `no such column: xxx`。给它一个专门的码，界面才能提示
    # 「请执行数据库迁移」，而不是笼统的「服务端内部错误」。
    DATABASE_ERROR = "KG.DATABASE_ERROR"

    # 500 未预期异常。兜底码的意义是「连错误响应都要是统一外壳」：
    # 否则客户端只能拿到 Starlette 的纯文本 500，前端的错误翻译层会把
    # axios 自己的 code（如 ERR_BAD_RESPONSE）当业务码渲染出来。
    INTERNAL_ERROR = "KG.INTERNAL_ERROR"

    # --- 账号体系：独立 AUTH 命名空间 ---
    # 认证失败与语义错误是两类事故，分开命名便于前端按域组织 i18n，
    # 也避免把「口令错」混进 KG.INVALID_REQUEST 这种泛化码里。
    INVALID_CREDENTIALS = "AUTH.INVALID_CREDENTIALS"
    TOKEN_EXPIRED = "AUTH.TOKEN_EXPIRED"
    FORBIDDEN = "AUTH.FORBIDDEN"
    USER_DISABLED = "AUTH.USER_DISABLED"
    REGISTRATION_CLOSED = "AUTH.REGISTRATION_CLOSED"
    WEAK_PASSWORD = "AUTH.WEAK_PASSWORD"
    OLD_PASSWORD_INVALID = "AUTH.OLD_PASSWORD_INVALID"
    RESET_TOKEN_INVALID = "AUTH.RESET_TOKEN_INVALID"
    EMAIL_TAKEN = "AUTH.EMAIL_TAKEN"
    USERNAME_TAKEN = "AUTH.USERNAME_TAKEN"


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
    ErrorCode.ALREADY_EXISTS: 409,
    ErrorCode.VALIDATION_VIOLATION: 422,
    ErrorCode.SOURCE_UNREACHABLE: 503,
    ErrorCode.REASONER_UNAVAILABLE: 503,
    ErrorCode.DATABASE_ERROR: 503,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.INVALID_CREDENTIALS: 401,
    ErrorCode.TOKEN_EXPIRED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.USER_DISABLED: 403,
    ErrorCode.REGISTRATION_CLOSED: 403,
    ErrorCode.WEAK_PASSWORD: 400,
    ErrorCode.OLD_PASSWORD_INVALID: 400,
    ErrorCode.RESET_TOKEN_INVALID: 400,
    ErrorCode.EMAIL_TAKEN: 409,
    ErrorCode.USERNAME_TAKEN: 409,
}
