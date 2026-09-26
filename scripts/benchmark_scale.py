"""规模压测（第三批 P2-03）：1 万实体 / 5 万事实的抽取基准。

生成合成源库（企业 1 万 + 任职关系 5 万），用 TestClient 驱动真实 API
全流程（建模→映射→抽取→图谱视图），输出各阶段耗时。

用法：
  KG_DATABASE_URL=sqlite:////tmp/benchmark.sqlite \\
  KG_BENCHMARK_SCALE=10000 \\
    server/.venv/bin/python scripts/benchmark_scale.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def data(response) -> dict:
    body = response.json()
    assert response.status_code < 400, body
    if "code" in body:
        assert body["code"] == "KG.OK", body
        return body["data"]
    return body


def post(client: TestClient, path: str, payload=None, headers=None) -> dict:
    return data(client.post("/api/v1" + path, json=payload, headers=headers))


def get(client: TestClient, path: str, headers=None) -> dict:
    return data(client.get("/api/v1" + path, headers=headers))


def login(client: TestClient) -> dict:
    import subprocess

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "seed_admin.py"),
            "--username",
            "bench_admin",
            "--email",
            "bench@example.org",
            "--password",
            "Bench-Admin-2026!",
        ],
        check=True,
        cwd=ROOT / "server",
    )
    body = data(
        client.post(
            "/api/v1/auth/login",
            json={"account": "bench_admin", "password": "Bench-Admin-2026!"},
        )
    )
    return {"Authorization": f"Bearer {body['access_token']}"}


def build_source(path: str, scale: int) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE company (
            id INTEGER PRIMARY KEY,
            name TEXT,
            region TEXT
        );
        CREATE TABLE work (
            id INTEGER PRIMARY KEY,
            employee_id INTEGER,
            company_id INTEGER
        );
        """
    )
    conn.executemany(
        "INSERT INTO company (id, name, region) VALUES (?, ?, ?)",
        ((i, f"公司{i}", f"区域{i % 7}") for i in range(1, scale + 1)),
    )
    facts = scale * 5
    conn.executemany(
        "INSERT INTO work (id, employee_id, company_id) VALUES (?, ?, ?)",
        ((i, i % (scale * 2), (i % scale) + 1) for i in range(1, facts + 1)),
    )
    conn.commit()
    conn.close()


def main() -> None:
    scale = int(os.environ.get("KG_BENCHMARK_SCALE", "10000"))
    tmp = Path("/tmp/kg-benchmark")
    tmp.mkdir(exist_ok=True)
    source_db = str(tmp / "source.sqlite")
    build_source(source_db, scale)
    print(f"source built: {scale} companies, {scale * 5} work rows")

    timings: dict[str, float] = {}

    def measure(name: str, fn):
        start = time.monotonic()
        result = fn()
        timings[name] = round(time.monotonic() - start, 2)
        return result

    with TestClient(app) as client:
        headers = login(client)
        ns = post(client, "/namespaces", {"prefix": "bench", "iri": "https://bench.example.org/"}, headers)
        post(
            client,
            "/entity-types",
            {"name": "Company", "namespace_id": ns["id"], "label_i18n": {"zh-CN": "公司", "en-US": "Company"}},
            headers,
        )
        entities = get(client, "/entity-types?page=1&page_size=5", headers)
        items = entities["items"] if isinstance(entities, dict) else entities
        company_id = next(e["id"] for e in items if e["name"] == "Company")
        post(client, f"/entity-types/{company_id}/publish", headers=headers)
        rel = post(
            client,
            "/relations",
            {
                "name": "WorksAt",
                "namespace_id": ns["id"],
                "label_i18n": {"zh-CN": "任职", "en-US": "WorksAt"},
                "domain_spec": {"type_id": company_id},
                "range_spec": {"type_id": company_id},
                "enable_attributes": False,
                "attribute_defs": [],
            },
            headers,
        )
        post(client, f"/relations/{rel['id']}/publish", headers=headers)
        member_ids = [company_id, rel["id"]]
        onto = post(
            client,
            "/ontologies",
            {
                "name": "BenchOnto",
                "iri": "https://bench.example.org/onto/",
                "label_i18n": {"zh-CN": "压测本体"},
                "ref_resource_ids": member_ids,
            },
            headers,
        )
        post(client, f"/ontologies/{onto['id']}/publish", headers=headers)

        ds = post(
            client,
            "/datasources",
            {"name": "BenchSource", "kind": "sqlite", "params": {"database": source_db}},
            headers,
        )
        measure("metadata_capture", lambda: post(client, f"/datasources/{ds['id']}/metadata/capture", headers=headers))

        mapping = post(
            client,
            "/mappings",
            {
                "name": "BenchMapping",
                "ontology_id": onto["id"],
                "draft": {
                    "entity_maps": [
                        {
                            "entity_type": "Company",
                            "table": "company",
                            "schema": "main",
                            "field_maps": [
                                {"target_attr": "name", "source_field": "name", "transform": "IDENTITY", "transform_params": None, "null_policy": "NULLABLE", "default_value": None},
                                {"target_attr": "region", "source_field": "region", "transform": "IDENTITY", "transform_params": None, "null_policy": "NULLABLE", "default_value": None},
                            ],
                            "key_fields": ["id"],
                            "match_keys": [],
                        }
                    ],
                    "rel_maps": [
                        {
                            "relation_type": "WorksAt",
                            "mode": "FK",
                            "table": "work",
                            "schema": "main",
                            "fk_field": "company_id",
                            "source": None,
                            "target": None,
                            "attributes": [],
                        }
                    ],
                },
            },
            headers,
        )
        published = post(client, f"/mappings/{mapping['id']}/publish", {"if_match": 0}, headers)

        run = {}

        def do_run():
            nonlocal run
            run = post(
                client,
                "/extraction/runs",
                {
                    "mapping_revision_id": published["id"],
                    "datasource_id": ds["id"],
                    "namespace": "https://bench.example.org/inst/",
                },
                headers,
            )

        measure("extraction_run", do_run)
        graph_id = run["graph_revision"]["id"]
        measure(
            "graph_view_full",
            lambda: get(client, f"/extraction/graph-view?graph_revision_id={graph_id}&node_limit=500", headers),
        )

    counts = run["run"]["counts"]
    summary = {
        "scale": {"entities": scale, "facts": scale * 5},
        "timings_seconds": timings,
        "run_status": run["run"]["status"],
        "counts": {k: v for k, v in counts.items() if isinstance(v, int)},
        "fingerprint": run["run"]["fingerprint"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    Path("/tmp/kg-benchmark/result.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    main()
