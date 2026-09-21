"""跨层共享的枚举（i18n L2：状态一律传枚举码，不传中文）。

这些值直接进数据库、API 响应与前端 i18n 码表，禁止中文。
"""

from __future__ import annotations

from enum import StrEnum


class ResourceKind(StrEnum):
    """model_resource 的资源种类。"""

    ENTITY = "ENTITY"
    DATATYPE_PROP = "DATATYPE_PROP"
    OBJECT_PROP = "OBJECT_PROP"
    ASSOC = "ASSOC"
    NAMESPACE = "NAMESPACE"
    DOMAIN = "DOMAIN"
    ONTOLOGY = "ONTOLOGY"


class ResourceStatus(StrEnum):
    """资源状态机：草稿 → 已发布。已发布即冻结，resource_revision 不可改。"""

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class ValidationState(StrEnum):
    """校验四态。未执行 ≠ 通过，这是产品哲学与合规底线。"""

    PASS = "PASS"
    VIOLATION = "VIOLATION"
    NA = "NA"
    NOT_RUN = "NOT_RUN"


class RunResult(StrEnum):
    """抽取运行结果。"""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RelMapMode(StrEnum):
    """关系映射三模式。"""

    FK = "FK"
    JUNCTION = "JUNCTION"
    ASSOCIATIVE = "ASSOCIATIVE"
