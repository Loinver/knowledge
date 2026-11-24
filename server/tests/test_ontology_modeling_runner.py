"""Unavailable semantic execution must fail closed and release worker capacity."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest
from app.semantics import ontology_modeling_validation as runner


def assert_not_run(result: list[dict], reason: str) -> None:
    assert {item["check_code"] for item in result} == {"M02", "M03", "M06"}
    assert all(item["state"] == "NOT_RUN" and item["required"] for item in result)
    assert all(item["code"] == reason for item in result)


def test_blocked_and_oversized_plans_never_start_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("worker must not start")

    monkeypatch.setattr(runner.subprocess, "Popen", unexpected)
    assert_not_run(
        runner.validate_candidate_semantics({"state": "BLOCKED"}, {}), "plan_blocked"
    )
    monkeypatch.setattr(runner, "MAX_INPUT_BYTES", 10)
    assert_not_run(
        runner.validate_candidate_semantics({"state": "COMPILED"}, {}),
        "semantic_input_too_large",
    )


def test_full_worker_pool_reports_not_run() -> None:
    assert runner._SLOTS.acquire(blocking=False)
    assert runner._SLOTS.acquire(blocking=False)
    try:
        assert_not_run(
            runner.validate_candidate_semantics({"state": "COMPILED"}, {}),
            "semantic_runner_busy",
        )
    finally:
        runner._SLOTS.release()
        runner._SLOTS.release()


@pytest.mark.parametrize(
    "output", ["{}", "[]", "invalid", '[{"check_code":"M02","state":"PASS"}]']
)
def test_invalid_worker_response_cannot_be_pass(
    monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    class Process:
        returncode = 0

        def communicate(self, *_args: Any, **_kwargs: Any) -> tuple[str, str]:
            return output, ""

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *_a, **_k: Process())
    result = runner.validate_candidate_semantics({"state": "COMPILED"}, {})
    assert all(item["state"] == "NOT_RUN" for item in result)
    assert runner._SLOTS.acquire(blocking=False)
    runner._SLOTS.release()


def test_timeout_kills_process_group_and_reaps_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class Process:
        pid = 987654
        returncode = -9

        def communicate(self, *_args: Any, **kwargs: Any) -> tuple[str, str]:
            if "timeout" in kwargs:
                calls.append("timeout")
                raise subprocess.TimeoutExpired("test-worker", kwargs["timeout"])
            calls.append("reaped")
            return "", ""

        def kill(self) -> None:
            calls.append("killed")

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *_a, **_k: Process())
    monkeypatch.setattr(
        runner.os, "killpg", lambda _pid, _signal: calls.append("killed")
    )
    assert_not_run(
        runner.validate_candidate_semantics({"state": "COMPILED"}, {}),
        "semantic_runner_timeout",
    )
    assert calls == ["timeout", "killed", "reaped"]
    assert runner._SLOTS.acquire(blocking=False)
    runner._SLOTS.release()


def test_invalid_state_or_duplicate_check_cannot_satisfy_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checks = [
        {"check_code": code, "state": "PASS", "coverage": "test"}
        for code in ("M02", "M03", "M06")
    ]

    class Process:
        returncode = 0

        def communicate(self, *_args: Any, **_kwargs: Any) -> tuple[str, str]:
            return json.dumps(checks), ""

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *_a, **_k: Process())
    checks.append(checks[0])
    assert_not_run(
        runner.validate_candidate_semantics({"state": "COMPILED"}, {}),
        "semantic_runner_invalid_response",
    )
    checks.pop()
    checks[0]["state"] = "SUCCESS"
    assert_not_run(
        runner.validate_candidate_semantics({"state": "COMPILED"}, {}),
        "semantic_runner_invalid_response",
    )
