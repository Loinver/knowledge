"""ORM 模型汇总导入。

集中导出是为了让 Alembic 的 target_metadata 与 SQLAlchemy 的
registry 能发现全部表；新增模型必须在这里登记。
"""

from __future__ import annotations

from app.models.data_access import (
    Datasource,
    Mapping,
    MappingPreview,
    MappingRevision,
    MetadataSnapshot,
)
from app.models.domain import (
    AssemblyTemplate,
    BusinessDomain,
    CanvasLayout,
    DomainMember,
    DomainRevision,
    Ontology,
    OntologyResourceRef,
    OntologyRevision,
)
from app.models.enums import (
    RelMapMode,
    ResourceKind,
    ResourceStatus,
    RunResult,
    ValidationState,
)
from app.models.extraction import (
    DerivedEdge,
    EntityIdentity,
    ExtractionRun,
    FactEvidence,
    GraphRevision,
    GraphTriple,
    Quarantine,
)
from app.models.governance import Rule
from app.models.resource import (
    ModelResource,
    Namespace,
    ResourceParent,
    ResourceRef,
    ResourceRevision,
)
from app.models.validation import ValidationReport, ValidationResult

__all__ = [
    "AssemblyTemplate",
    "BusinessDomain",
    "CanvasLayout",
    "Datasource",
    "DerivedEdge",
    "DomainMember",
    "DomainRevision",
    "EntityIdentity",
    "ExtractionRun",
    "FactEvidence",
    "GraphRevision",
    "GraphTriple",
    "Mapping",
    "MappingPreview",
    "MappingRevision",
    "MetadataSnapshot",
    "ModelResource",
    "Namespace",
    "Ontology",
    "OntologyResourceRef",
    "OntologyRevision",
    "Quarantine",
    "RelMapMode",
    "ResourceKind",
    "ResourceParent",
    "ResourceRef",
    "ResourceRevision",
    "ResourceStatus",
    "Rule",
    "RunResult",
    "ValidationReport",
    "ValidationResult",
    "ValidationState",
]
