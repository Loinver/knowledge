"""Compile the bounded modeling plan into executable RDF/SHACL, entirely offline."""

from __future__ import annotations

from itertools import combinations
from typing import Any

from pyshacl import validate
from rdflib import OWL, RDF, RDFS, SH, XSD, BNode, Graph, Literal, URIRef
from rdflib.collection import Collection

from app.models.enums import ValidationState
from app.schemas.ontology import OntologyExportFormat
from app.semantics.ontology_rdf import (
    OntologyRdfMetadata,
    OntologyRdfResource,
    serialize_ontology_rdf,
)
from app.semantics.rdflib_backend import RdflibBackend

_DATATYPES = {
    "string": XSD.string,
    "integer": XSD.integer,
    "decimal": XSD.decimal,
    "boolean": XSD.boolean,
    "date": XSD.date,
    "anyURI": XSD.anyURI,
}
_FEATURES = {
    "functional": OWL.FunctionalProperty,
    "inverse_functional": OWL.InverseFunctionalProperty,
    "symmetric": OWL.SymmetricProperty,
    "transitive": OWL.TransitiveProperty,
}


def axiom_rules(plan: dict[str, Any]) -> list[dict[str, Any]]:
    rules = []
    for axiom in plan.get("axioms", []):
        graph = Graph()
        kind = axiom["kind"]
        if kind in {"EQUIVALENT_CLASSES", "DISJOINT_CLASSES"}:
            predicate = (
                OWL.equivalentClass
                if kind == "EQUIVALENT_CLASSES"
                else OWL.disjointWith
            )
            for left, right in combinations(axiom["iris"], 2):
                graph.add((URIRef(left), predicate, URIRef(right)))
            target = axiom["iris"][0]
        elif kind == "SUBPROPERTY":
            target = axiom["sub_iri"]
            graph.add((URIRef(target), RDFS.subPropertyOf, URIRef(axiom["super_iri"])))
        else:
            raise ValueError("unsupported_modeling_axiom")
        rules.append(
            {
                "candidate_id": axiom["candidate_id"],
                "language": "OWL",
                "target_iri": target,
                "severity": "VIOLATION",
                "execution": "AUTO",
                "expression": graph.serialize(format="turtle"),
            }
        )
    return rules


def constraint_rules(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Return generated rule bodies; callers assign DB identifiers and provenance."""
    result = []
    for constraint in plan["constraints"]:
        graph = Graph()
        shape, prop = BNode(), BNode()
        target = URIRef(constraint["target_iri"])
        graph.add((shape, RDF.type, SH.NodeShape))
        graph.add((shape, SH.targetClass, target))
        graph.add((shape, SH.property, prop))
        graph.add(
            (
                prop,
                SH.severity,
                {"INFO": SH.Info, "WARNING": SH.Warning, "VIOLATION": SH.Violation}[
                    constraint["severity"]
                ],
            )
        )
        spec = constraint["spec"]
        path: URIRef | BNode = URIRef(spec["path"]["iri"])
        if spec["path"]["inverse"]:
            inverse = BNode()
            graph.add((inverse, SH.inversePath, path))
            path = inverse
        graph.add((prop, SH.path, path))
        kind = spec["kind"]
        if kind == "CARDINALITY":
            graph.add((prop, SH.minCount, Literal(spec["min"])))
            if spec["max"] is not None:
                graph.add((prop, SH.maxCount, Literal(spec["max"])))
        elif kind == "ENUM":
            values = BNode()
            Collection(
                graph,
                values,
                [
                    Literal(item["lexical"], datatype=_DATATYPES[item["datatype"]])
                    for item in spec["allowed"]
                ],
            )
            graph.add((prop, SH["in"], values))
        elif kind == "PATTERN":
            graph.add((prop, SH.pattern, Literal(spec["regex"])))
            if spec["flags"]:
                graph.add((prop, SH.flags, Literal(spec["flags"])))
        elif kind == "NUMERIC_RANGE":
            for field, inclusive, exclusive in (
                ("minimum", SH.minInclusive, SH.minExclusive),
                ("maximum", SH.maxInclusive, SH.maxExclusive),
            ):
                if spec[field] is not None:
                    graph.add(
                        (
                            prop,
                            inclusive if spec[field + "_inclusive"] else exclusive,
                            Literal(spec[field], datatype=XSD.decimal),
                        )
                    )
        elif kind == "CLASS_MEMBERSHIP":
            graph.add((prop, SH["class"], URIRef(spec["allowed_class"]["iris"][0])))
        else:
            raise ValueError("unsupported_modeling_constraint")
        result.append(
            {
                "candidate_id": constraint["candidate_id"],
                "language": "SHACL",
                "target_iri": str(target),
                "severity": constraint["severity"],
                "execution": "AUTO",
                "expression": graph.serialize(format="turtle"),
            }
        )
    return result


def validate_modeling_plan(
    plan: dict[str, Any], context: dict[str, Any]
) -> list[dict[str, Any]]:
    """Validate TBox and shape syntax, without claiming instance conformance."""
    if plan["state"] != "COMPILED":
        return [
            {
                "check_code": "M02",
                "state": "NOT_RUN",
                "coverage": "candidate_tbox",
                "code": "plan_blocked",
            },
            {
                "check_code": "M03",
                "state": "NOT_RUN",
                "coverage": "shape_syntax",
                "code": "plan_blocked",
            },
        ]
    try:
        resources = {
            int(rid): OntologyRdfResource.model_validate(value)
            for rid, value in context["working_payloads"].items()
        }
        for asset in context["asset_catalog"].values():
            resources.setdefault(
                asset["id"], OntologyRdfResource.model_validate(asset["snapshot"])
            )
        content = serialize_ontology_rdf(
            OntologyRdfMetadata.model_validate(context["ontology_metadata"]),
            resources,
            revision=context["published_revision"],
            rdf_format=OntologyExportFormat.TURTLE,
            rules=context["working_rules"],
        )
        graph = Graph().parse(data=content, format="turtle")
        for operation in plan["resources"]:
            subject = URIRef(operation["iri"])
            kind = operation["kind"]
            if kind == "REUSE":
                # Explicit catalogs include the selected frozen resource closure.
                asset = context["asset_catalog"][operation["handle"]]
                graph.add(
                    (
                        subject,
                        RDF.type,
                        {
                            "CLASS": OWL.Class,
                            "DATA_PROPERTY": OWL.DatatypeProperty,
                            "OBJECT_PROPERTY": OWL.ObjectProperty,
                        }[asset["kind"]],
                    )
                )
            elif kind == "NEW_CLASS":
                graph.add((subject, RDF.type, OWL.Class))
                for parent in operation["parents"]:
                    graph.add((subject, RDFS.subClassOf, URIRef(parent)))
            elif kind == "NEW_DATA_PROPERTY":
                graph.add((subject, RDF.type, OWL.DatatypeProperty))
                graph.add((subject, RDFS.domain, URIRef(operation["owner_iri"])))
                graph.add((subject, RDFS.range, _DATATYPES[operation["datatype"]]))
            elif kind == "NEW_OBJECT_PROPERTY":
                graph.add((subject, RDF.type, OWL.ObjectProperty))
                graph.add((subject, RDFS.domain, URIRef(operation["domain_iri"])))
                graph.add((subject, RDFS.range, URIRef(operation["range_iri"])))
                for feature, enabled in operation["features"].items():
                    if enabled:
                        graph.add((subject, RDF.type, _FEATURES[feature]))
        for link in plan["inverse_links"]:
            graph.add(
                (URIRef(link["left_iri"]), OWL.inverseOf, URIRef(link["right_iri"]))
            )
        for rule in axiom_rules(plan):
            graph.parse(data=rule["expression"], format="turtle")
        backend = RdflibBackend()
        outcome = backend.check_consistency(graph.serialize(format="turtle"))
        checks = [
            {
                "check_code": "M02",
                "state": outcome.state.value,
                "coverage": "candidate_tbox_owl2rl",
                "code": "owl2rl_consistency",
                "params": {"errors": (outcome.raw or {}).get("errors", [])[:10]},
            }
        ]
        rules = constraint_rules(plan)
        if not rules:
            checks.append(
                {
                    "check_code": "M03",
                    "state": "NA",
                    "coverage": "shape_syntax",
                    "code": "no_candidate_constraints",
                }
            )
        else:
            shapes = Graph()
            for rule in rules:
                shapes.parse(data=rule["expression"], format="turtle")
            # This invokes meta-SHACL, and only attests shape syntax. An empty
            # instance graph does not stand in for validating business instances.
            validate(
                Graph(),
                shacl_graph=shapes,
                meta_shacl=True,
                advanced=False,
                js=False,
                do_owl_imports=False,
            )
            checks.append(
                {
                    "check_code": "M03",
                    "state": "PASS",
                    "coverage": "shape_syntax",
                    "code": "meta_shacl_compiled",
                }
            )
        return checks
    except Exception as exc:
        # Safe closed result: do not return RDF content or parser exception text.
        return [
            {
                "check_code": "M02",
                "state": ValidationState.NOT_RUN.value,
                "coverage": "candidate_tbox",
                "code": "semantic_execution_unavailable",
                "params": {"type": type(exc).__name__},
            },
            {
                "check_code": "M03",
                "state": "NOT_RUN",
                "coverage": "shape_syntax",
                "code": "semantic_execution_unavailable",
            },
        ]
