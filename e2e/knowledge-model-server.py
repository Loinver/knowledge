"""Isolated protocol fixture, not a real model or production fallback."""

from __future__ import annotations

import json
import os
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def send(self, status: int, body: dict) -> None:
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except BrokenPipeError:
            pass

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
