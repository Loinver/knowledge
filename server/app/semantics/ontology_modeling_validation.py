"""Bounded offline execution of candidate semantic and example checks."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
from contextlib import suppress
from pathlib import Path
from typing import Any, Never

MAX_INPUT_BYTES = 2_000_000
MAX_OUTPUT_BYTES = 2_000_000
TIMEOUT_SECONDS = 45
_SLOTS = threading.BoundedSemaphore(2)
_SERVER = Path(__file__).resolve().parents[2]


def _not_run(reason: str) -> list[dict[str, Any]]:
    return [
        {
            "check_code": code,
            "state": "NOT_RUN",
            "required": True,
            "code": reason,
            "coverage": coverage,
        }
        for code, coverage in (
            ("M02", "candidate_tbox_owl2rl"),
            ("M03", "shape_syntax"),
            ("M06", "generated_positive_negative_examples"),
        )
    ]


def validate_candidate_semantics(plan: dict, context: dict) -> list[dict[str, Any]]:
    if plan["state"] != "COMPILED":
        return _not_run("plan_blocked")
    raw = json.dumps(
        {"plan": plan, "context": context}, ensure_ascii=False, allow_nan=False
    )
    if len(raw.encode()) > MAX_INPUT_BYTES:
        return _not_run("semantic_input_too_large")
    if not _SLOTS.acquire(blocking=False):
        return _not_run("semantic_runner_busy")
    try:
        process = subprocess.Popen(
            [sys.executable, "-B", "-m", "app.semantics.ontology_modeling_validation"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=_SERVER,
            start_new_session=True,
        )
        try:
            stdout, _ = process.communicate(raw, timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.communicate()
            return _not_run("semantic_runner_timeout")
        if process.returncode != 0 or len(stdout.encode()) > MAX_OUTPUT_BYTES:
            return _not_run("semantic_runner_failed")
        response = json.loads(stdout)
        if (
            not isinstance(response, list)
            or len(response) != 3
            or not all(isinstance(item, dict) for item in response)
            or {item.get("check_code") for item in response} != {"M02", "M03", "M06"}
            or any(
                item.get("state") not in {"PASS", "VIOLATION", "NA", "NOT_RUN"}
                or item.get("required", True) is not True
                or not isinstance(item.get("coverage"), str)
                for item in response
            )
        ):
            return _not_run("semantic_runner_invalid_response")
        return response
    except (OSError, ValueError, TypeError, AttributeError):
        return _not_run("semantic_runner_unavailable")
    finally:
        _SLOTS.release()


def _worker() -> None:
    import socket

    def blocked(*_args: Any, **_kwargs: Any) -> Never:
        raise RuntimeError("modeling validation forbids network")

    for method in ("connect", "connect_ex", "sendto"):
        setattr(socket.socket, method, blocked)
    socket.create_connection = blocked
    socket.getaddrinfo = blocked
    if os.name == "posix":
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (20, 25))
        if sys.platform.startswith("linux"):
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    from app.semantics.ontology_modeling import validate_modeling_plan
    from app.semantics.ontology_modeling_examples import validate_modeling_examples

    try:
        request = json.loads(sys.stdin.read(MAX_INPUT_BYTES + 1))
        checks = validate_modeling_plan(request["plan"], request["context"])
        checks.append(validate_modeling_examples(request["plan"], request["context"]))
    except Exception:
        checks = _not_run("semantic_execution_unavailable")
    print(json.dumps(checks, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    _worker()
