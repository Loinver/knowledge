"""五类经营知识场景的端到端装配脚本（验收辅助，只写隔离库）。

用 FastAPI TestClient 驱动真实 API，按业务顺序执行九环节：
命名空间 → 类型/关系 → 业务域/本体 → 规则（DATA/DERIVATION） → 数据源 →
映射（自引用/多态/融合/带属性） → 发布 → 抽取（四阶段） → 结果核对。

用法（server venv 内执行）：
  KG_DATABASE_URL=sqlite:////tmp/five-scenarios.sqlite \\
    server/.venv/bin/python scripts/seed_five_scenarios.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DB = ROOT / "samples" / "enterprise_demo.sqlite"
ADMIN = ("scenario_admin", "scenario-admin@example.org", "Scenario-Admin-2026!")

_auth: dict[str, str] = {}


def data(client: TestClient, response) -> dict:
    body = response.json()
    assert response.status_code < 400, body
    if isinstance(body, dict) and "code" in body:
        assert body["code"] == "KG.OK", body
        return body["data"]
    return body


def post(client: TestClient, path: str, payload: dict | None = None) -> dict:
    return data(client, client.post("/api/v1" + path, json=payload, headers=_auth))


def get(client: TestClient, path: str) -> dict:
    return data(client, client.get("/api/v1" + path, headers=_auth))


def login(client: TestClient) -> None:
    """引导管理员并登录（隔离库，脚本专用）。"""
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "seed_admin.py"),
            "--username",
            ADMIN[0],
            "--email",
            ADMIN[1],
            "--password",
            ADMIN[2],
        ],
        check=True,
        cwd=ROOT / "server",
    )
    body = data(
        client,
        client.post(
            "/api/v1/auth/login",
            json={"account": ADMIN[0], "password": ADMIN[2]},
        ),
    )
    _auth["Authorization"] = f"Bearer {body['access_token']}"


def field(target: str, source: str, transform: str = "IDENTITY") -> dict:
    return {
        "target_attr": target,
        "source_field": source,
        "transform": transform,
        "transform_params": None,
        "null_policy": "NULLABLE",
        "default_value": None,
    }


def main() -> None:
    assert os.environ.get("KG_DATABASE_URL", "").startswith("sqlite:///"), (
        "请用 KG_DATABASE_URL 指向隔离的元数据库"
    )
    with TestClient(app) as client:
        login(client)
        # 1. 命名空间
        ns = post(
            client,
            "/namespaces",
            {
                "prefix": "scene",
                "iri": "https://example.org/scene/",
                "protected": False,
                "label_i18n": {"zh-CN": "五场景验收", "en-US": "Five scenarios"},
            },
        )

        # 2. 实体类型
        entity_specs = [
            ("Enterprise", "企业", [("name", "string"), ("creditCode", "string")]),
            ("Department", "部门", [("name", "string")]),
            ("Person", "人员", [("name", "string")]),
            ("Project", "项目", [("name", "string"), ("startDate", "date")]),
            ("Contract", "合同", [("title", "string"), ("signDate", "date"), ("amount", "decimal")]),
            ("Partner", "客商", [("name", "string")]),
        ]
        entities: dict[str, int] = {}
        for name, label, props in entity_specs:
            res = post(
                client,
                "/entity-types",
                {
                    "name": name,
                    "namespace_id": ns["id"],
                    "label_i18n": {"zh-CN": label, "en-US": name},
                    "data_props": [
                        {
                            "name": prop,
                            "datatype": datatype,
                            "nullable": True,
                            "label_i18n": {"zh-CN": prop, "en-US": prop},
                        }
                        for prop, datatype in props
                    ],
                },
            )
            post(client, f"/entity-types/{res['id']}/publish")
            entities[name] = res["id"]

        # 3. 关系类型（自引用/带属性/多方）
        relation_specs = [
            ("BelongsTo", "所属部门", "Department", "Department", True, []),
            ("InvestsIn", "投资持股", "Person", "Enterprise", True, [("pct", "decimal")]),
            ("HoldsEquityIn", "持股", "Enterprise", "Enterprise", True, [("pct", "decimal")]),
            ("MemberOf", "参与项目", "Project", "Person", False, []),
            ("TradeWith", "交易往来", "Enterprise", "Enterprise", True, [("amount", "decimal"), ("direction", "string")]),
            ("HasParty", "合同签约方", "Contract", "Enterprise", True, [("partyRole", "string")]),
            ("SupplementaryTo", "补充协议", "Contract", "Contract", False, []),
        ]
        relations: dict[str, int] = {}
        for name, label, domain, range_, with_attrs, attrs in relation_specs:
            res = post(
                client,
                "/relations",
                {
                    "name": name,
                    "namespace_id": ns["id"],
                    "label_i18n": {"zh-CN": label, "en-US": name},
                    "domain_spec": {"type_id": entities[domain]},
                    "range_spec": {"type_id": entities[range_]},
                    "enable_attributes": with_attrs,
                    "attribute_defs": [
                        {"name": attr, "datatype": datatype, "nullable": True}
                        for attr, datatype in attrs
                    ],
                },
            )
            post(client, f"/relations/{res['id']}/publish")
            relations[name] = res["id"]

        # 4. 业务域 + 本体
        member_ids = [*entities.values(), *relations.values()]
        domain = post(
            client,
            "/domains",
            {
                "name": "ScenarioDomain",
                "iri": "https://example.org/scene/domain#operations",
                "label_i18n": {"zh-CN": "经营知识域", "en-US": "Business knowledge"},
                "member_ids": member_ids,
            },
        )
        post(client, f"/domains/{domain['id']}/publish")
        # 5. 规则（DATA 数据规则 + DERIVATION 派生规则），随本体创建时钉入
        rules = [
            ("R-ORG-ACYCLIC", "DATA", {"op": "acyclic", "edge": "BelongsTo"}),
            ("R-EQUITY-SUM", "DATA", {"op": "sum_le", "edge": "InvestsIn", "attr": "pct", "max": 100, "group": "object"}),
            ("R-CREDIT-UNIQUE", "DATA", {"op": "unique_attr", "type": "Enterprise", "attr": "creditCode"}),
            ("R-CONTRACT-PARTY", "DATA", {"op": "required_edge", "edge": "HasParty", "type": "Contract", "min": 1}),
            ("R-COLLEAGUE", "DERIVATION", {"op": "co_occurrence", "via_edge": "MemberOf", "derive_edge": "ColleagueOf"}),
            ("R-INDIRECT-HOLDING", "DERIVATION", {"op": "product_chain", "edge": "HoldsEquityIn", "attr": "pct", "derive_edge": "IndirectlyHolds", "min_value": 0.01}),
        ]
        rule_ids = []
        for identifier, language, expression in rules:
            rule = post(
                client,
                "/governance/rules",
                {
                    "identifier": identifier,
                    "name_i18n": {"zh-CN": identifier, "en-US": identifier},
                    "category": "scene",
                    "source_kind": "ENTERPRISE",
                    "source_reference": "SCENARIO-POLICY-01",
                    "target_iri": "https://example.org/scene/Enterprise",
                    "severity": "VIOLATION",
                    "language": language,
                    "expression": json.dumps(expression),
                    "execution": "AUTO",
                    "positive_example": "",
                    "negative_example": "",
                },
            )
            rule_ids.append(rule["id"])
        ontology = post(
            client,
            "/ontologies",
            {
                "name": "ScenarioOntology",
                "iri": "https://example.org/scene/onto/",
                "label_i18n": {"zh-CN": "五场景本体", "en-US": "Scenario ontology"},
                "ref_resource_ids": member_ids,
                "rule_ids": rule_ids,
            },
        )
        post(client, f"/ontologies/{ontology['id']}/publish")

        # 6. 数据源 + 元数据
        ds = post(
            client,
            "/datasources",
            {"name": "FiveScenarios", "kind": "sqlite", "params": {"database": str(SAMPLE_DB)}},
        )
        post(client, f"/datasources/{ds['id']}/metadata/capture")

        # 7. 映射（自引用 / 多态判别 / 跨表业务键融合 / 带属性）并发布
        candidates = [
            {"field": "person_id", "ref_table": "hr_employee", "when": "PERSON", "ref_entity_type": "Person"},
            {"field": "enterprise_id", "ref_table": "enterprise", "when": "ENTERPRISE", "ref_entity_type": "Enterprise"},
        ]
        mapping = post(
            client,
            "/mappings",
            {
                "name": "ScenarioMapping",
                "ontology_id": ontology["id"],
                "draft": {
                    "entity_maps": [
                        {
                            "entity_type": "Enterprise",
                            "table": "enterprise",
                            "schema": "main",
                            "field_maps": [field("name", "name"), field("creditCode", "credit_code")],
                            "key_fields": ["id"],
                            "match_keys": [],
                        },
                        {
                            "entity_type": "Department",
                            "table": "org_department",
                            "schema": "main",
                            "field_maps": [field("name", "name")],
                            "key_fields": ["id"],
                            "match_keys": [],
                        },
                        {
                            "entity_type": "Person",
                            "table": "hr_employee",
                            "schema": "main",
                            "field_maps": [field("name", "name")],
                            "key_fields": ["id"],
                            "match_keys": [],
                        },
                        {
                            "entity_type": "Project",
                            "table": "pm_project",
                            "schema": "main",
                            "field_maps": [field("name", "name"), field("startDate", "start_date", "DATE")],
                            "key_fields": ["id"],
                            "match_keys": [],
                        },
                        {
                            "entity_type": "Contract",
                            "table": "ct_contract",
                            "schema": "main",
                            "field_maps": [field("title", "title"), field("signDate", "sign_date", "DATE"), field("amount", "amount")],
                            "key_fields": ["id"],
                            "match_keys": [],
                        },
                        {
                            "entity_type": "Partner",
                            "table": "crm_customer",
                            "schema": "main",
                            "field_maps": [field("name", "name")],
                            "key_fields": ["id"],
                            "match_keys": ["credit_code"],
                        },
                        {
                            "entity_type": "Partner",
                            "table": "crm_supplier",
                            "schema": "main",
                            "field_maps": [field("name", "name")],
                            "key_fields": ["id"],
                            "match_keys": ["credit_code"],
                        },
                    ],
                    "rel_maps": [
                        {
                            "relation_type": "BelongsTo",
                            "mode": "FK",
                            "table": "org_department",
                            "schema": "main",
                            "fk_field": "parent_id",
                            "source": None,
                            "target": None,
                            "attributes": [],
                        },
                        {
                            "relation_type": "InvestsIn",
                            "mode": "ASSOCIATIVE",
                            "table": "eq_equity_holding",
                            "schema": "main",
                            "fk_field": None,
                            "source": {
                                "field": "shareholder_id",
                                "ref_table": "eq_shareholder",
                                "ref_field": "id",
                                "type_field": "shareholder_type",
                                "candidates": [candidates[0]],
                                "via": {"table": "eq_shareholder", "field": "shareholder_id", "ref_field": "id"},
                            },
                            "target": {"field": "investee_enterprise_id", "ref_table": "enterprise", "ref_field": "id"},
                            "attributes": [{"attr": "pct", "field": "ownership_pct"}],
                        },
                        {
                            "relation_type": "HoldsEquityIn",
                            "mode": "ASSOCIATIVE",
                            "table": "eq_equity_holding",
                            "schema": "main",
                            "fk_field": None,
                            "source": {
                                "field": "shareholder_id",
                                "ref_table": "eq_shareholder",
                                "ref_field": "id",
                                "type_field": "shareholder_type",
                                "candidates": [candidates[1]],
                                "via": {"table": "eq_shareholder", "field": "shareholder_id", "ref_field": "id"},
                            },
                            "target": {"field": "investee_enterprise_id", "ref_table": "enterprise", "ref_field": "id"},
                            "attributes": [{"attr": "pct", "field": "ownership_pct"}],
                        },
                        {
                            "relation_type": "MemberOf",
                            "mode": "JUNCTION",
                            "table": "pm_project_member",
                            "schema": "main",
                            "fk_field": None,
                            "source": {"field": "project_id", "ref_table": "pm_project", "ref_field": "id"},
                            "target": {"field": "member_id", "ref_table": "hr_employee", "ref_field": "id"},
                            "attributes": [],
                        },
                        {
                            "relation_type": "TradeWith",
                            "mode": "ASSOCIATIVE",
                            "table": "crm_trade_transaction",
                            "schema": "main",
                            "fk_field": None,
                            "source": {"field": "own_enterprise_id", "ref_table": "enterprise", "ref_field": "id"},
                            "target": {"field": "partner_enterprise_id", "ref_table": "enterprise", "ref_field": "id"},
                            "attributes": [{"attr": "amount", "field": "amount"}, {"attr": "direction", "field": "direction"}],
                        },
                        {
                            "relation_type": "HasParty",
                            "mode": "ASSOCIATIVE",
                            "table": "ct_contract_party",
                            "schema": "main",
                            "fk_field": None,
                            "source": {"field": "contract_id", "ref_table": "ct_contract", "ref_field": "id"},
                            "target": {"field": "enterprise_id", "ref_table": "enterprise", "ref_field": "id"},
                            "attributes": [{"attr": "partyRole", "field": "party_role"}],
                        },
                        {
                            "relation_type": "SupplementaryTo",
                            "mode": "FK",
                            "table": "ct_contract",
                            "schema": "main",
                            "fk_field": "parent_contract_id",
                            "source": None,
                            "target": None,
                            "attributes": [],
                        },
                    ],
                },
            },
        )
        client.put(
            f"/api/v1/mappings/{mapping['id']}/draft",
            json={
                "draft": client.get(f"/api/v1/mappings/{mapping['id']}/draft").json()["data"],
                "if_match": 0,
            },
        )
        published = post(client, f"/mappings/{mapping['id']}/publish", {"if_match": 0})

        # 8. 抽取（四阶段）并输出核对数据
        result = post(
            client,
            "/extraction/runs",
            {
                "mapping_revision_id": published["id"],
                "datasource_id": ds["id"],
                "namespace": "https://example.org/scene/instances/",
            },
        )
        run = result["run"]
        summary = {
            "run_id": run["id"],
            "status": run["status"],
            "counts": {
                key: value
                for key, value in run["counts"].items()
                if key not in ("rule_results", "validation_summary")
            },
            "rule_results": run["counts"].get("rule_results", []),
            "validation_summary": run["counts"].get("validation_summary", {}),
            "graph_revision_id": (result.get("graph_revision") or {}).get("id"),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
