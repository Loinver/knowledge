"""Isolated protocol fixture, not a real model or production fallback."""

from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def fictional_candidate(context: dict) -> dict:
    """Purely fictional candidate; handles come only from this test request."""
    namespace = next(iter(context["namespace_catalog"]))
    spans = context["source_catalog"]["source:request"]
    span = next(iter(spans))
    suffix = context["context_token"][-8:]

    def metadata(label: str) -> dict:
        return {
            "labels": {"zh-CN": label, "en-US": None},
            "definitions": {"zh-CN": None, "en-US": None},
            "synonyms": [],
        }

    def evidence(dependencies: list[str]) -> dict:
        return {
            "basis": "SOURCE",
            "source_refs": [{"source_handle": "source:request", "span_handle": span}],
            "rationale_i18n": {"zh-CN": "仅依据虚构验收需求", "en-US": None},
            "depends_on": dependencies,
            "uncertainty_ids": [],
        }

    def reference(candidate_id: str) -> dict:
        return {"kind": "CANDIDATE", "candidate_id": candidate_id}

    resources = [
        {
            "candidate_id": candidate_id,
            "spec": {
                "kind": "NEW_CLASS",
                "namespace_handle": namespace,
                "local_name": name + suffix,
                "metadata": metadata(label),
                "parents": [],
            },
            "evidence": evidence([]),
        }
        for candidate_id, name, label in [
            ("c:Device", "FictionalDevice", "虚构设备"),
            ("c:Team", "FictionalTeam", "虚构团队"),
        ]
    ]
    resources.append(
        {
            "candidate_id": "c:AssignedTo",
            "spec": {
                "kind": "NEW_OBJECT_PROPERTY",
                "namespace_handle": namespace,
                "local_name": "fictionalAssignedTo" + suffix,
                "metadata": metadata("虚构分配关系"),
                "domain": {"mode": "ONE", "refs": [reference("c:Device")]},
                "range": {"mode": "ONE", "refs": [reference("c:Team")]},
                "inverse_of": None,
                "features": dict.fromkeys(
                    [
                        "functional",
                        "inverse_functional",
                        "symmetric",
                        "transitive",
                        "asymmetric",
                        "reflexive",
                        "irreflexive",
                    ],
                    False,
                ),
            },
            "evidence": evidence(["c:Device", "c:Team"]),
        }
    )
    return {
        "schema_version": "ontology-candidate/1.0",
        "context_token": context["context_token"],
        "profile_echo": context["profile"],
        "scope": {
            "goal_i18n": {"zh-CN": "纯虚构浏览器验收", "en-US": None},
            "out_of_scope_i18n": [],
            "assumptions_i18n": [],
        },
        "ontology_metadata": None,
        "resources": resources,
        "axioms": [],
        "constraints": [],
        "questions": [],
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        pass

    def send(self, status: int, body: dict) -> None:
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        with suppress(BrokenPipeError):
            self.wfile.write(encoded)

    def do_GET(self) -> None:
        self.send(200, {"test_fixture": True})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        text = json.dumps(body, ensure_ascii=False)
        if "LIMIT_TEST" in text:
            self.send(429, {"error": {"type": "rate_limit_error"}})
            return
        if "SLOW_TEST" in text:
            time.sleep(3)
        if self.path.endswith("/embeddings"):
            self.send(
                200,
                {
                    "data": [
                        {
                            "index": index,
                            "embedding": [1.0, 0.0, 0.0]
                            if any(term in value for term in ("维护", "检修", "保养"))
                            else [0.0, 1.0, 0.0],
                        }
                        for index, value in enumerate(body["input"])
                    ]
                },
            )
            return
        context = json.loads(body["messages"][-1]["content"])
        if context.get("schema_version") == "ontology-candidate/1.0":
            content = fictional_candidate(context)
            self.send(
                200,
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": json.dumps(content)},
                        }
                    ]
                },
            )
            return
        sources = context["evidence"]
        content = {
            "status": "ANSWERED" if sources else "INSUFFICIENT_EVIDENCE",
            "citations": [
                {"chunk_id": item["chunk_id"], "quote": item["text"]}
                for item in sources[:2]
            ],
        }
        self.send(200, {"choices": [{"message": {"content": json.dumps(content)}}]})


if __name__ == "__main__":
    directory = Path(os.environ["KG_E2E_TEMP_DIR"]).resolve()
    if not directory.is_relative_to(
        Path(tempfile.gettempdir()).resolve()
    ) or not directory.name.startswith("knowledge-e2e-"):
        raise SystemExit("Test model requires an isolated temporary directory")
    ThreadingHTTPServer(("127.0.0.1", 8134), Handler).serve_forever()
