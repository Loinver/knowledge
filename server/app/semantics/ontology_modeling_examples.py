"""Bounded, offline witnesses shared by modeling validation and apply receipts."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.schemas.governance import RuleCreate
from app.semantics.ontology_modeling import constraint_rules
from app.semantics.rule_examples import run_examples

EXAMPLE_VERSION = "ontology-modeling-examples/2"
_XSD = "http://www.w3.org/2001/XMLSchema#"


def _reject(code: ErrorCode, reason: str, **params: Any) -> KGError:
    return KGError(code, {"reason": reason, **params})


def _iri(value: str) -> str:
    if not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value) or any(
        char.isspace() or ord(char) < 32 or char in '<>"{}|^`\\' for char in value
    ):
        raise _reject(ErrorCode.INVALID_IRI, "invalid_plan_iri")
    return f"<{value}>"


def _literal(value: str, datatype: str = "string") -> str:
    if datatype not in {"string", "integer", "decimal", "boolean", "date", "anyURI"}:
        raise _reject(ErrorCode.ONTOLOGY_CONSTRUCT_UNSUPPORTED, "unsupported_datatype")
    return json.dumps(value, ensure_ascii=False) + "^^" + _iri(_XSD + datatype)


def _pattern_samples(pattern: str, flags: str) -> tuple[str, str]:
    """Construct witnesses for the compiler's concatenated, anchored regex subset."""
    rest, pieces, negative = pattern[1:-1], [], None
    while rest:
        if rest[0] == "[":
            end = 1
            while end < len(rest) and (rest[end] != "]" or rest[end - 1] == "\\"):
                end += 1
            atom, rest = rest[: end + 1], rest[end + 1 :]
        elif rest[0] == "\\":
            atom, rest = rest[:2], rest[2:]
        else:
            atom, rest = rest[0], rest[1:]
        count = 1
        if rest.startswith(("*", "?", "+")):
            count = 0 if rest[0] in "*?" else 1
            rest = rest[1:]
        elif rest.startswith("{"):
            end = rest.index("}")
            count = int(rest[1:end].split(",")[0])
            rest = rest[end + 1 :]
        match_flags = re.I if "i" in flags else 0
        chars = [chr(i) for i in range(32, 127)] + ["\n", "中"]
        matching = [c for c in chars if re.fullmatch(atom, c, match_flags)]
        if not matching:
            raise _reject(
                ErrorCode.ONTOLOGY_CONSTRUCT_UNSUPPORTED, "pattern_witness_missing"
            )
        pieces.append(matching[0] * count)
        if count and negative is None:
            wrong = next(
                (c for c in chars if not re.fullmatch(atom, c, match_flags)), None
            )
            if wrong is not None:
                negative = "".join(pieces[:-1]) + wrong
    positive = "".join(pieces)
    return positive, negative if negative is not None else positive + "!\n!"


def _examples(constraint: dict, plan: dict, catalog: dict) -> tuple[str, str]:
    spec = constraint["spec"]
    target, prop = _iri(constraint["target_iri"]), _iri(spec["path"]["iri"])
    property_record = next(
        record
        for record in [*plan["resources"], *catalog.values()]
        if record["iri"] == spec["path"]["iri"] and record["kind"] != "REUSE"
    )
    datatype = property_record.get("datatype", "string")
    object_path = property_record.get("kind") in {
        "NEW_OBJECT_PROPERTY",
        "OBJECT_PROPERTY",
    }

    def values(count: int) -> list[str]:
        if count > 1000:
            raise _reject(ErrorCode.ONTOLOGY_CONSTRUCT_UNSUPPORTED, "example_budget")
        if object_path:
            return [f"<urn:modeling:example:value:{i}>" for i in range(count)]
        if datatype == "boolean":
            if count > 2:
                raise _reject(
                    ErrorCode.ONTOLOGY_CONSTRUCT_UNSUPPORTED,
                    "boolean_witness_cardinality",
                )
            lexical = ["true", "false"][:count]
        elif datatype == "integer":
            lexical = [str(i + 1) for i in range(count)]
        elif datatype == "decimal":
            lexical = [f"{i + 1}.0" for i in range(count)]
        elif datatype == "date":
            start = date(2000, 1, 1)
            lexical = [(start + timedelta(days=i)).isoformat() for i in range(count)]
        elif datatype == "anyURI":
            lexical = [f"urn:example:value:{i}" for i in range(count)]
        else:
            lexical = [f"value:{i}" for i in range(count)]
        return [_literal(value, datatype) for value in lexical]

    kind = spec["kind"]
    if kind == "CARDINALITY":
        if spec["min"] == 0 and spec["max"] is None:
            raise _reject(
                ErrorCode.ONTOLOGY_CONSTRUCT_UNSUPPORTED, "vacuous_cardinality"
            )
        positive = values(spec["min"])
        negative = values(0 if spec["min"] else spec["max"] + 1)
    elif kind == "ENUM":
        value = spec["allowed"][0]
        positive = [_literal(value["lexical"], value["datatype"])]
        if datatype == "date":
            allowed_dates = {date.fromisoformat(v["lexical"]) for v in spec["allowed"]}
            excluded_date = date(2000, 1, 1)
            while excluded_date in allowed_dates:
                excluded_date += timedelta(days=1)
            negative = [_literal(excluded_date.isoformat(), "date")]
        else:
            excluded = "outside-generated-enumeration"
            while any(v["lexical"] == excluded for v in spec["allowed"]):
                excluded += "x"
            negative = [_literal(excluded)]
    elif kind == "PATTERN":
        matching_text, rejected_text = _pattern_samples(spec["regex"], spec["flags"])
        positive, negative = [_literal(matching_text)], [_literal(rejected_text)]
    elif kind == "NUMERIC_RANGE":
        low = Decimal(spec["minimum"]) if spec["minimum"] is not None else None
        high = Decimal(spec["maximum"]) if spec["maximum"] is not None else None
        if low is None and high is None:
            raise _reject(ErrorCode.INVALID_REQUEST, "empty_numeric_range")
        if datatype == "integer":
            # Round bounds individually. int +/- 1 stays exact even for bounds
            # larger than Decimal's arithmetic precision.
            lower = (
                None
                if low is None
                else (
                    int(low.to_integral_value(rounding=ROUND_CEILING))
                    if spec["minimum_inclusive"]
                    else int(low.to_integral_value(rounding=ROUND_FLOOR)) + 1
                )
            )
            upper = (
                None
                if high is None
                else (
                    int(high.to_integral_value(rounding=ROUND_FLOOR))
                    if spec["maximum_inclusive"]
                    else int(high.to_integral_value(rounding=ROUND_CEILING)) - 1
                )
            )
            if lower is not None:
                accepted_integer, rejected_integer = lower, lower - 1
            else:
                assert upper is not None
                accepted_integer, rejected_integer = upper, upper + 1
            # Match the compiler's policy: an empty integer value space blocks
            # the candidate instead of claiming an omitted value is a witness.
            if lower is not None and upper is not None and lower > upper:
                raise _reject(ErrorCode.VALIDATION_VIOLATION, "empty_integer_range")
            positive = [_literal(str(accepted_integer), "integer")]
            negative = [_literal(str(rejected_integer), "integer")]
        else:
            if low is not None and high is not None:
                valid_number = (low + high) / 2
            elif low is not None:
                valid_number = low + 1
            else:
                assert high is not None
                valid_number = high - 1
            if low is not None:
                invalid_number = low - 1
            else:
                assert high is not None
                invalid_number = high + 1
            positive, negative = (
                [_literal(str(valid_number), datatype)],
                [_literal(str(invalid_number), datatype)],
            )
    else:
        positive, negative = (
            ["<urn:modeling:example:allowed>"],
            ["<urn:modeling:example:excluded>"],
        )

    def graph(objects: list[str], *, allowed: bool) -> str:
        focus = "<urn:modeling:example:focus>"
        lines = [f"{focus} a {target} ."]
        for obj in objects:
            lines.append(
                f"{obj} {prop} {focus} ."
                if spec["path"]["inverse"]
                else f"{focus} {prop} {obj} ."
            )
            if kind == "CLASS_MEMBERSHIP" and allowed:
                lines.append(f"{obj} a {_iri(spec['allowed_class']['iris'][0])} .")
        return "\n".join(lines)

    return graph(positive, allowed=True), graph(negative, allowed=False)


def validate_modeling_examples(plan: dict[str, Any], context: dict[str, Any]) -> dict:
    """Return required M06 with fixed examples; never attest business instances."""
    result: dict[str, Any] = {
        "check_code": "M06",
        "required": True,
        "coverage": "generated_positive_negative_examples",
        "state": "NOT_RUN",
        "code": "constraint_examples_not_run",
        "params": {"version": EXAMPLE_VERSION, "examples": {}},
    }
    if plan["state"] != "COMPILED":
        result["code"] = "plan_blocked"
        return result
    if not plan["constraints"]:
        result.update(state="NA", code="no_candidate_constraints")
        return result
    try:
        bodies = {rule["candidate_id"]: rule for rule in constraint_rules(plan)}
        for constraint in plan["constraints"]:
            cid = constraint["candidate_id"]
            body = bodies[cid]
            positive, negative = _examples(constraint, plan, context["asset_catalog"])
            definition = RuleCreate(
                identifier=cid,
                name_i18n={"zh-CN": cid},
                category="ONTOLOGY_MODELING",
                source_kind="ENTERPRISE",
                source_reference=EXAMPLE_VERSION,
                **{key: value for key, value in body.items() if key != "candidate_id"},
                positive_example=positive,
                negative_example=negative,
            )
            yes, no = run_examples(definition)
            if not yes["conforms"] or no["conforms"]:
                result.update(state="VIOLATION", code="constraint_examples_invalid")
                result["params"]["candidate_id"] = cid
                return result
            result["params"]["examples"][cid] = {
                "positive_example": positive,
                "negative_example": negative,
            }
    except KGError as exc:
        result["code"] = exc.code.value
        result["params"]["reason"] = exc.params.get(
            "reason", "example_execution_failed"
        )
        return result
    except (KeyError, ValueError, TypeError, OverflowError, re.error):
        result["code"] = "constraint_examples_unavailable"
        return result
    result.update(state="PASS", code="generated_examples_verified")
    return result
