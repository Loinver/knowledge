"""完整导入的依赖预检与原子恢复编排；事务提交由 API 边界负责。"""

from __future__ import annotations

import hashlib
import json
from collections import Counter

from sqlalchemy import or_, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.domain.enum_dictionary_service import create_dictionary
from app.domain.iri_service import PREFIX_PATTERN
from app.domain.ontology_service import create_ontology, publish_ontology
from app.domain.status_service import publish_resource
from app.iri import is_valid_name, is_valid_namespace
from app.models.domain import Ontology
from app.models.enum_dictionary import EnumDictionary
from app.models.enums import ResourceKind, ResourceStatus
from app.models.resource import (
    DatatypePropDetail,
    ModelResource,
    Namespace,
    ObjectPropDetail,
    ResourceParent,
    ResourceRef,
)
from app.schemas.ontology import OntologyCreate
from app.schemas.ontology_import import ImportFormat, OntologyImportConflict
from app.schemas.ontology_restore import (
    OntologyRestorePreview,
    OntologyRestoreRequest,
    OntologyRestoreResult,
    RestoreResourceOut,
)
from app.schemas.relation import CardinalitySpec
from app.semantics.ontology_restore import RestoreDocument, parse_restore_document


def content_digest(rdf_format: ImportFormat, content: str) -> str:
    return hashlib.sha256(f"{rdf_format}\n{content}".encode()).hexdigest()


def _lock_restore_transaction(session: Session) -> None:
    """Keep the recheck and writes atomic until the API commits or rolls back.

    The locks also conflict with ordinary SQL writers, without their cooperation.
    SQLite needs a write even for an empty ontology table; PostgreSQL needs table
    locks because a not-yet-existing ontology IRI cannot be row-locked. Ordinary
    ontology creation still permits duplicate IRIs *after* this transaction ends.
    """
    with session.no_autoflush:
        connection = session.connection()
        dialect = connection.dialect.name
        try:
            if dialect == "sqlite":
                # Acquire SQLite's database write lock without changing any row.
                connection.execute(text("UPDATE ontology SET id = id WHERE 1 = 0"))
            elif dialect == "postgresql":
                # A pre-existing repeatable-read snapshot could miss a writer
                # that committed before our lock. Never accept such a snapshot.
                if connection.get_isolation_level() != "READ COMMITTED":
                    raise KGError(
                        ErrorCode.VALIDATION_VIOLATION,
                        {"reason": "restore_requires_read_committed"},
                    )
                connection.execute(
                    text(
                        "LOCK TABLE namespace, ontology "
                        "IN SHARE ROW EXCLUSIVE MODE NOWAIT"
                    )
                )
            else:
                raise KGError(
                    ErrorCode.VALIDATION_VIOLATION,
                    {"reason": "restore_database_unsupported", "dialect": dialect},
                )
        except DBAPIError as exc:
            sqlite_code = getattr(exc.orig, "sqlite_errorcode", None)
            sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(
                exc.orig, "pgcode", None
            )
            # pg8000 exposes PostgreSQL error fields as its first argument.
            if (
                exc.orig is not None
                and exc.orig.args
                and isinstance(exc.orig.args[0], dict)
            ):
                sqlstate = exc.orig.args[0].get("C", sqlstate)
            if (
                dialect == "sqlite"
                and isinstance(sqlite_code, int)
                and sqlite_code & 0xFF in {5, 6}  # SQLITE_BUSY / SQLITE_LOCKED
            ) or (dialect == "postgresql" and sqlstate in {"55P03", "40001", "40P01"}):
                raise KGError(
                    ErrorCode.REVISION_CONFLICT, {"reason": "restore_preview_stale"}
                ) from exc
            raise


def inspect_restore(
    session: Session, rdf_format: ImportFormat, content: str
) -> tuple[RestoreDocument, OntologyRestorePreview]:
    document = parse_restore_document(rdf_format, content)
    conflicts = list(document.issues)

    def conflict(iri: str, code: str, **params: object) -> None:
        conflicts.append(OntologyImportConflict(iri=iri, code=code, params=params))

    metadata = document.metadata
    if metadata is None:
        conflict("", "MISSING_ONTOLOGY_METADATA")
    else:
        if not is_valid_name(metadata.name):
            conflict(metadata.iri, "INVALID_NAME", name=metadata.name)
        if (
            session.scalar(
                select(Ontology.id).where(
                    or_(Ontology.name == metadata.name, Ontology.iri == metadata.iri)
                )
            )
            is not None
        ):
            conflict(metadata.iri, "ONTOLOGY_EXISTS", name=metadata.name)

    items = {resource.iri: resource for resource in document.resources}
    if len(items) != len(document.resources) or not items:
        conflict("", "DUPLICATE_OR_EMPTY_RESOURCES")
    for name, count in Counter(resource.name for resource in items.values()).items():
        if count > 1:
            conflict("", "DUPLICATE_RESOURCE_NAME", name=name)

    namespaces: dict[str, str] = {}
    namespace_prefixes: dict[str, str] = {}
    for resource in items.values():
        if not is_valid_namespace(
            resource.namespace_iri
        ) or not PREFIX_PATTERN.fullmatch(resource.namespace_prefix):
            conflict(resource.iri, "INVALID_NAMESPACE")
        previous = namespaces.setdefault(
            resource.namespace_prefix, resource.namespace_iri
        )
        if previous != resource.namespace_iri:
            conflict(resource.iri, "NAMESPACE_PREFIX_CONFLICT")
        previous_prefix = namespace_prefixes.setdefault(
            resource.namespace_iri, resource.namespace_prefix
        )
        if previous_prefix != resource.namespace_prefix:
            conflict(resource.iri, "NAMESPACE_IRI_CONFLICT")
        if len(resource.name) > 128 or len(resource.iri) > 640:
            conflict(resource.iri, "RESOURCE_IDENTIFIER_TOO_LONG")
        if resource.kind != ResourceKind.DATATYPE_PROP:
            if not is_valid_name(resource.name):
                conflict(resource.iri, "INVALID_NAME", name=resource.name)
            if resource.iri != resource.namespace_iri + resource.name:
                conflict(resource.iri, "RESOURCE_IRI_MISMATCH")
        if resource.kind not in {
            ResourceKind.ENTITY,
            ResourceKind.ASSOC,
            ResourceKind.DATATYPE_PROP,
            ResourceKind.OBJECT_PROP,
        }:
            conflict(resource.iri, "UNSUPPORTED_RESOURCE_KIND")
        for dependency in [
            *resource.parent_iris,
            *(ref.target_iri for ref in resource.refs),
        ]:
            if dependency not in items:
                conflict(resource.iri, "MISSING_DEPENDENCY", target=dependency)

    for prefix, iri in namespaces.items():
        for existing_namespace in session.execute(
            select(Namespace.prefix, Namespace.iri).where(
                or_(Namespace.prefix == prefix, Namespace.iri == iri)
            )
        ):
            if existing_namespace.iri != iri or existing_namespace.prefix != prefix:
                conflict(iri, "NAMESPACE_PREFIX_CONFLICT", prefix=prefix)

    dictionaries = {item.iri: item for item in document.enums}
    for item in document.enums:
        if (
            session.scalar(
                select(EnumDictionary.id).where(
                    EnumDictionary.name == item.definition.name
                )
            )
            is not None
        ):
            conflict(item.iri, "ENUM_NAME_EXISTS", name=item.definition.name)
    for name, count in Counter(item.definition.name for item in document.enums).items():
        if count > 1:
            conflict("", "ENUM_NAME_CONFLICT", name=name)

    previews: list[RestoreResourceOut] = []
    for resource in items.values():
        existing = session.scalar(
            select(ModelResource).where(
                or_(
                    ModelResource.iri == resource.iri,
                    ModelResource.name == resource.name,
                )
            )
        )
        if existing is not None:
            conflict(resource.iri, "RESOURCE_EXISTS", resource_id=existing.id)
        if resource.enum_iri and resource.enum_iri not in dictionaries:
            conflict(resource.iri, "MISSING_ENUM_DICTIONARY")
        previews.append(
            RestoreResourceOut(
                iri=resource.iri,
                name=resource.name,
                kind=resource.kind,
                namespace_iri=resource.namespace_iri,
                namespace_prefix=resource.namespace_prefix,
                dependencies=sorted(
                    {
                        *resource.parent_iris,
                        *(ref.target_iri for ref in resource.refs),
                        *([resource.enum_iri] if resource.enum_iri else []),
                    }
                ),
                existing_resource_id=existing.id if existing else None,
            )
        )

    # Bind acceptance to both the file and the observed conflict/dependency state.
    state = {
        "content": content_digest(rdf_format, content),
        "conflicts": [item.model_dump() for item in conflicts],
        "resources": [item.model_dump() for item in previews],
    }
    digest = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    return document, OntologyRestorePreview(
        preview_digest=digest,
        name=metadata.name if metadata else None,
        root_iri=metadata.iri if metadata else None,
        source_revision=document.source_revision,
        triple_count=document.triple_count,
        resources=previews,
        enum_names=[item.definition.name for item in document.enums],
        conflicts=conflicts,
        unsupported_triples=document.unsupported_triples,
        can_apply=not conflicts and not document.unsupported_triples,
    )


def restore_ontology(
    session: Session, payload: OntologyRestoreRequest
) -> OntologyRestoreResult:
    """Recheck the reviewed file and create a complete local revision without overwrite.

    Source identifiers for resources are retained. Database IDs and revision numbers
    belong to this installation; source revisions are never used as local identities.
    Any exception must roll back the caller's transaction, including all new namespaces.
    """
    if payload.ontology_id is not None:
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "restore_creates_ontology"})
    _lock_restore_transaction(session)
    document, preview = inspect_restore(session, payload.format, payload.content)
    if preview.preview_digest != payload.preview_digest:
        raise KGError(ErrorCode.REVISION_CONFLICT, {"reason": "restore_preview_stale"})
    if not preview.can_apply or document.metadata is None:
        raise KGError(
            ErrorCode.VALIDATION_VIOLATION,
            {"reason": "restore_blocked", "conflict_count": len(preview.conflicts)},
        )

    namespaces: dict[str, Namespace] = {}
    for item in document.resources:
        if item.namespace_prefix in namespaces:
            continue
        namespace = session.scalar(
            select(Namespace)
            .where(Namespace.prefix == item.namespace_prefix)
            .execution_options(populate_existing=True)
        )
        if namespace is not None and namespace.iri != item.namespace_iri:
            raise KGError(
                ErrorCode.REVISION_CONFLICT, {"reason": "restore_preview_stale"}
            )
        if namespace is None:
            namespace = Namespace(prefix=item.namespace_prefix, iri=item.namespace_iri)
            session.add(namespace)
            session.flush()
        namespaces[item.namespace_prefix] = namespace
    dictionaries = {
        item.iri: create_dictionary(session, item.definition) for item in document.enums
    }
    resources: dict[str, ModelResource] = {}
    for item in document.resources:
        resource = ModelResource(
            name=item.name,
            iri=item.iri,
            namespace_id=namespaces[item.namespace_prefix].id,
            kind=item.kind,
            label_i18n=item.label_i18n,
            definition_i18n=item.definition_i18n,
        )
        session.add(resource)
        resources[item.iri] = resource
    session.flush()
    for item in document.resources:
        resource = resources[item.iri]
        for parent in item.parent_iris:
            session.add(
                ResourceParent(child_id=resource.id, parent_id=resources[parent].id)
            )
        for ref in item.refs:
            session.add(
                ResourceRef(
                    source_id=resource.id,
                    target_id=resources[ref.target_iri].id,
                    role=ref.role,
                )
            )
        if item.datatype is not None:
            prop = item.datatype.model_dump(
                exclude={"name", "label_i18n", "definition_i18n"}
            )
            if item.enum_iri is not None:
                dictionary = dictionaries[item.enum_iri]
                prop.update(
                    enum_dict_id=dictionary.id, enum_dict_revision=dictionary.revision
                )
            session.add(
                DatatypePropDetail(
                    resource_id=resource.id, prop_name=item.datatype.name, **prop
                )
            )
        if item.object_prop is not None:
            detail = item.object_prop
            domain = CardinalitySpec.model_validate(detail["domain_cardinality"])
            range_spec = CardinalitySpec.model_validate(detail["range_cardinality"])
            session.add(
                ObjectPropDetail(
                    resource_id=resource.id,
                    domain_min=domain.min,
                    domain_max=domain.max,
                    domain_role_i18n=detail["domain_role_i18n"],
                    domain_cardinality_role_i18n=domain.role_label_i18n,
                    range_min=range_spec.min,
                    range_max=range_spec.max,
                    range_role_i18n=detail["range_role_i18n"],
                    range_cardinality_role_i18n=range_spec.role_label_i18n,
                    owl=detail["owl"],
                )
            )
    session.flush()
    for resource in resources.values():
        if resource.status == ResourceStatus.DRAFT:
            publish_resource(session, resource)
    metadata = document.metadata
    ontology = create_ontology(
        session,
        OntologyCreate(
            name=metadata.name,
            iri=metadata.iri,
            label_i18n=metadata.label_i18n or {},
            definition_i18n=metadata.definition_i18n,
            ref_resource_ids=[item.id for item in resources.values()],
        ),
    )
    publish_ontology(session, ontology)
    return OntologyRestoreResult(
        ontology_id=ontology.id,
        current_revision=ontology.current_revision,
        source_revision=document.source_revision,
        created_resource_count=len(resources),
        created_dictionary_count=len(dictionaries),
    )
