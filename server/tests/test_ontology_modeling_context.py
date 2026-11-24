"""真实发布快照到建模 catalog 的窄回归；只使用独立临时数据库。"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from app.core.db import Base
from app.domain.iri_service import register_namespace
from app.domain.ontology_modeling_context import prepare_context
from app.domain.ontology_modeling_plan import compile_candidate
from app.domain.ontology_modeling_service import (
    get_candidate_revision,
    save_generated,
    validate_proposal,
)
from app.domain.ontology_service import create_ontology, publish_ontology
from app.domain.relation_service import create_relation_type
from app.domain.status_service import get_revision, publish_resource
from app.domain.type_service import create_entity_type
from app.models.domain import Ontology, OntologyResourceRef
from app.models.enums import ResourceStatus, ValidationState
from app.models.resource import (
    DatatypePropDetail,
    ModelResource,
    ObjectPropDetail,
    ResourceRef,
)
from app.schemas.ontology import OntologyCreate
from app.schemas.ontology_modeling import ModelingCreate
from app.schemas.ontology_modeling_candidate import OntologyCandidate
from app.schemas.relation import EndpointSpec, OwlFeatures, RelationTypeCreate
from app.schemas.type import DataTypePropCreate, EntityTypeCreate
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

NS = "https://example.org/context/"


@pytest.fixture()
def session(tmp_path: Path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path}/context.db")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection: Any, _record: Any) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            yield db
    finally:
        engine.dispose()


@dataclass
class FrozenModel:
    ontology: Ontology
    owner: ModelResource
    child: ModelResource
    target: ModelResource
    relation: ModelResource
    inverse: ModelResource
    prop: ModelResource


def _published(session: Session, datatype: str = "integer") -> FrozenModel:
    namespace = register_namespace(session, "ctx", NS)

    def entity(
        name: str, parents: list[int], props: list[DataTypePropCreate]
    ) -> ModelResource:
        resource = create_entity_type(
            session,
            EntityTypeCreate(
                name=name,
                namespace_id=namespace.id,
                label_i18n={"zh-CN": f"测试类型 {name}"},
                parent_ids=parents,
                data_props=props,
            ),
        )
        publish_resource(session, resource)
        return resource

    owner = entity(
        "Owner",
        [],
        [
            DataTypePropCreate(
                name="value", datatype=datatype, label_i18n={"zh-CN": "测试数据属性"}
            )
        ],
    )
    child = entity("Child", [owner.id], [])
    target = entity("Target", [], [])

    def relation(
        name: str,
        domain: int,
        range_: int,
        *,
        inverse: int | None = None,
        functional: bool = False,
    ) -> ModelResource:
        resource = create_relation_type(
            session,
            RelationTypeCreate(
                name=name,
                namespace_id=namespace.id,
                label_i18n={"zh-CN": f"测试关系 {name}"},
                domain_spec=EndpointSpec(type_id=domain),
                range_spec=EndpointSpec(type_id=range_),
                inverse_of=inverse,
                owl=OwlFeatures(functional=functional),
            ),
        )
        publish_resource(session, resource)
        return resource

    forward = relation("Links", owner.id, target.id, functional=True)
    backward = relation("LinkedBy", target.id, owner.id, inverse=forward.id)
    prop = session.scalar(
        select(ModelResource).where(ModelResource.iri == f"{owner.iri}/value")
    )
    assert prop is not None
    ontology = create_ontology(
        session,
        OntologyCreate(
            name="ContextModel",
            iri=f"{NS}Ontology",
            label_i18n={"zh-CN": "目录测试本体"},
            ref_resource_ids=[owner.id, child.id, target.id, forward.id, backward.id],
        ),
    )
    publish_ontology(session, ontology)
    # Represent explicit published member pins, including the inherited owner.
    for ref in session.scalars(
        select(OntologyResourceRef).where(
            OntologyResourceRef.ontology_id == ontology.id
        )
    ):
        ref.pinned_revision = 1
    session.flush()
    return FrozenModel(ontology, owner, child, target, forward, backward, prop)


def _context(session: Session, model: FrozenModel) -> dict:
    return prepare_context(
        session,
        ModelingCreate(
            target_ontology_id=model.ontology.id,
            target_draft_id=f"ontology:{model.ontology.id}:working",
            base_edit_revision=model.ontology.edit_revision,
            text="核验已授权冻结目录",
            namespace_ids=[model.owner.namespace_id],
            authorize_model_transfer=True,
        ),
    )


def _asset(context: dict, resource: ModelResource) -> dict:
    return context["asset_catalog"][f"asset:{resource.id}:1"]


def _candidate(
    context: dict,
    target: ModelResource,
    prop: ModelResource,
    spec: dict,
    *,
    inverse: bool = False,
) -> OntologyCandidate:
    evidence = {
        "basis": "PROPOSAL",
        "source_refs": [],
        "rationale_i18n": {"zh-CN": "窄回归构造", "en-US": None},
        "depends_on": [],
        "uncertainty_ids": [],
    }

    def ref(resource: ModelResource) -> dict:
        return {"kind": "CATALOG", "handle": f"asset:{resource.id}:1"}

    return OntologyCandidate.model_validate(
        {
            "schema_version": "ontology-candidate/1.0",
            "context_token": context["context_token"],
            "profile_echo": "BUSINESS",
            "scope": {
                "goal_i18n": {"zh-CN": "复用冻结资产", "en-US": None},
                "out_of_scope_i18n": [],
                "assumptions_i18n": [],
            },
            "ontology_metadata": None,
            "resources": [
                {
                    "candidate_id": "c:reuse",
                    "spec": {
                        "kind": "REUSE",
                        "handle": f"asset:{prop.id}:1",
                        "expected_kind": _asset(context, prop)["kind"],
                        "attach_to_ontology": False,
                    },
                    "evidence": evidence,
                }
            ],
            "axioms": [],
            "constraints": [
                {
                    "candidate_id": "c:constraint",
                    "target_class": ref(target),
                    "spec": {
                        **spec,
                        "path": {"property": ref(prop), "inverse": inverse},
                    },
                    "severity": "VIOLATION",
                    "evidence": evidence,
                }
            ],
            "questions": [],
        }
    )


def _compile(context: dict, candidate: OntologyCandidate) -> dict:
    return compile_candidate(
        candidate,
        namespace_catalog=context["namespace_catalog"],
        asset_catalog=context["asset_catalog"],
        source_catalog=context["source_catalog"],
        context_token=context["context_token"],
        profile=context["profile"],
    )


def test_relation_roles_and_owl_are_projected_from_real_frozen_payload(
    session: Session,
) -> None:
    model = _published(session)
    context = _context(session, model)
    relation, inverse = _asset(context, model.relation), _asset(context, model.inverse)
    assert relation["domain_iri"] == model.owner.iri
    assert relation["range_iri"] == model.target.iri
    assert inverse["domain_iri"] == model.target.iri
    assert inverse["range_iri"] == model.owner.iri
    assert inverse["inverse_iri"] == model.relation.iri
    assert relation["features"] == relation["snapshot"]["object_prop"]["owl"]
    assert relation["features"]["functional"] is True


@pytest.mark.parametrize("inverse", [False, True])
def test_reuse_relation_cardinality_compiles_in_each_direction(
    session: Session, inverse: bool
) -> None:
    model = _published(session)
    context = _context(session, model)
    target = model.target if inverse else model.child
    plan = _compile(
        context,
        _candidate(
            context,
            target,
            model.relation,
            {"kind": "CARDINALITY", "min": 1, "max": 1},
            inverse=inverse,
        ),
    )
    assert plan["state"] == "COMPILED", plan["issues"]
    assert plan["issues"] == []
    assert plan["constraints"][0]["spec"]["path"]["iri"] == model.relation.iri


@pytest.mark.parametrize(
    ("datatype", "lexical"),
    [
        ("string", "VALID"),
        ("integer", "2"),
        ("decimal", "2.5"),
        ("boolean", "true"),
        ("date", "2026-11-20"),
        ("anyURI", "https://example.org/value"),
    ],
)
def test_reuse_datatype_enumeration_uses_frozen_self_detail(
    session: Session, datatype: str, lexical: str
) -> None:
    model = _published(session, datatype)
    context = _context(session, model)
    prop = _asset(context, model.prop)
    assert prop["snapshot"]["datatype_props"][0]["role"] == "self"
    assert prop["snapshot"]["datatype_props"][0]["iri"] == prop["iri"]
    assert prop["datatype"] == datatype
    assert prop["owner_iri"] == model.owner.iri
    plan = _compile(
        context,
        _candidate(
            context,
            model.child,
            model.prop,
            {"kind": "ENUM", "allowed": [{"datatype": datatype, "lexical": lexical}]},
        ),
    )
    assert plan["state"] == "COMPILED", plan["issues"]


def test_frozen_owl_features_enforce_reuse_cardinality_conflict(
    session: Session,
) -> None:
    model = _published(session)
    context = _context(session, model)
    plan = _compile(
        context,
        _candidate(
            context,
            model.child,
            model.relation,
            {"kind": "CARDINALITY", "min": 2, "max": 2},
        ),
    )
    assert plan["state"] == "BLOCKED"
    assert [issue["code"] for issue in plan["issues"]] == [
        "KG.CANDIDATE_CARDINALITY_FEATURE_CONFLICT"
    ]
    assert plan["issues"][0]["state"] == "VIOLATION"


def test_numeric_reuse_constraint_is_validated_with_real_fixed_context(
    session: Session,
) -> None:
    model = _published(session)
    context = _context(session, model)
    candidate = _candidate(
        context,
        model.child,
        model.prop,
        {
            "kind": "NUMERIC_RANGE",
            "minimum": "1",
            "maximum": "10",
            "minimum_inclusive": True,
            "maximum_inclusive": True,
        },
    )
    proposal = save_generated(
        session,
        actor_id="context-review",
        request_key="context-regression",
        request_digest="offline-fixture",
        context=context,
        candidate=candidate,
        model_provenance={"model": "offline-fixture"},
    )
    revision = get_candidate_revision(session, proposal)
    report = validate_proposal(session, proposal, 1, revision.candidate_digest)
    assert report.can_apply, report.model_dump()
    assert all(
        check.state == ValidationState.PASS for check in report.checks if check.required
    )


def test_live_relation_and_datatype_edits_do_not_change_pinned_projection(
    session: Session,
) -> None:
    model = _published(session)
    before = _context(session, model)
    endpoint = session.scalar(
        select(ResourceRef).where(
            ResourceRef.source_id == model.relation.id,
            ResourceRef.role == "relation_domain",
        )
    )
    assert endpoint is not None
    endpoint.target_id = model.target.id
    detail = session.get(ObjectPropDetail, model.relation.id)
    assert detail is not None
    detail.owl = {"functional": False}
    prop = session.get(DatatypePropDetail, model.prop.id)
    assert prop is not None
    prop.datatype = "string"
    model.relation.status = ResourceStatus.DRAFT
    model.owner.status = ResourceStatus.DRAFT
    publish_resource(session, model.relation)
    publish_resource(session, model.owner)
    after = _context(session, model)
    assert after["asset_catalog"] == before["asset_catalog"]
    assert after["fingerprint"] == before["fingerprint"]
    assert _asset(after, model.prop)["datatype"] == "integer"
    assert _asset(after, model.relation)["domain_iri"] == model.owner.iri


@pytest.mark.parametrize("missing", ["endpoint", "datatype"])
def test_missing_frozen_projection_data_is_not_replaced_by_live_values(
    session: Session, missing: str
) -> None:
    model = _published(session)
    resource = model.relation if missing == "endpoint" else model.prop
    frozen = get_revision(session, resource.id, 1)
    frozen.payload = (
        {
            **frozen.payload,
            "resource_refs": [
                ref
                for ref in frozen.payload["resource_refs"]
                if ref["role"] != "relation_domain"
            ],
        }
        if missing == "endpoint"
        else {
            key: value
            for key, value in frozen.payload.items()
            if key != "datatype_props"
        }
    )
    context = _context(session, model)
    spec = (
        {"kind": "CARDINALITY", "min": 1, "max": 1}
        if missing == "endpoint"
        else {
            "kind": "NUMERIC_RANGE",
            "minimum": "1",
            "maximum": "10",
            "minimum_inclusive": True,
            "maximum_inclusive": True,
        }
    )
    plan = _compile(context, _candidate(context, model.child, resource, spec))
    assert plan["state"] == "BLOCKED"
    assert any(
        issue["code"] == "KG.CANDIDATE_MISSING_PROPERTY_CONTEXT"
        and issue["state"] == "NOT_RUN"
        for issue in plan["issues"]
    )
