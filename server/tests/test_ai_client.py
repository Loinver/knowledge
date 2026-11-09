from __future__ import annotations

import asyncio
import gzip
import json
import logging
import math

import httpx
import pytest
from app.core.ai_client import CompatibleModel, ModelEndpoint
from app.core.errors import KGError


def client(monkeypatch, handler, *, timeout: float = 1) -> CompatibleModel:
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)),
    )
    return CompatibleModel(
        ModelEndpoint(
            "https://example.org/v1",
            "secret-for-test",
            "test-model",
            timeout_seconds=timeout,
        )
    )


def test_chat_and_embedding_protocol_and_response_order(monkeypatch) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.headers["Authorization"] == "Bearer secret-for-test"
        assert payload["model"] == "test-model"
        if request.url.path.endswith("embeddings"):
            assert payload["encoding_format"] == "float"
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": 1, "embedding": [0, 3]},
                        {"index": 0, "embedding": [2, 0]},
                    ]
                },
            )
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "answer"}}]}
        )

    model = client(monkeypatch, respond)
    assert asyncio.run(model.chat("context", "question")) == "answer"
    assert asyncio.run(model.embed(["first", "second"])) == [[1, 0], [0, 1]]
    assert "secret-for-test" not in repr(model.endpoint)


def test_legacy_suggestions_keep_payload_and_json_array_contract(monkeypatch) -> None:
    from app.core import llm

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["temperature"] == 0.2
        assert "max_tokens" not in payload
        assert payload["messages"][0] == {"role": "system", "content": "system"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '```json\n[{"name":"Example"}]\n```'}}
                ]
            },
        )

    client(monkeypatch, respond)
    monkeypatch.setattr(
        llm,
        "_require_configured",
        lambda: ("https://example.org/v1", "secret-for-test", "test-model", 1),
    )
    assert llm.chat_json("system", "user") == [{"name": "Example"}]


def test_only_connection_failures_retry_and_no_sensitive_logs(
    monkeypatch, caplog
) -> None:
    requests = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ConnectError("secret upstream failure", request=request)
        return httpx.Response(429, text="secret response body")

    model = client(monkeypatch, respond)
    with caplog.at_level(logging.INFO), pytest.raises(KGError) as failure:
        asyncio.run(model.chat("secret prompt", "secret question"))
    assert len(requests) == 2
    assert failure.value.params["reason"] == "model_rate_or_quota_limit"
    assert "secret" not in str(failure.value.params) + caplog.text


def test_read_error_is_not_replayed(monkeypatch) -> None:
    calls = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("sensitive text", request=request)

    model = client(monkeypatch, respond)
    with pytest.raises(KGError) as failure:
        asyncio.run(model.chat("a", "b"))
    assert len(calls) == 1
    assert failure.value.params["reason"] == "model_timeout"


@pytest.mark.parametrize(
    "data",
    [
        [],
        [{"index": 0, "embedding": [0, 0]}],
        [{"index": 1, "embedding": [1, 0]}],
        [{"index": 0, "embedding": [True, 1]}],
        [{"index": 0, "embedding": ["1", 1]}],
        [{"index": 0, "embedding": [10**400, 1]}],
    ],
)
def test_invalid_embeddings_are_errors_not_empty_results(monkeypatch, data) -> None:
    model = client(monkeypatch, lambda _: httpx.Response(200, json={"data": data}))
    with pytest.raises(KGError) as failure:
        asyncio.run(model.embed(["input"]))
    assert failure.value.code.value == "KG.LLM_RESPONSE_INVALID"


def test_absolute_timeout_and_cancellation(monkeypatch) -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return httpx.Response(200, json={})

    model = client(monkeypatch, respond, timeout=0.02)
    with pytest.raises(KGError) as failure:
        asyncio.run(model.chat("a", "b"))
    assert failure.value.params["reason"] == "model_timeout"

    async def cancelled() -> None:
        task = asyncio.create_task(model.chat("a", "b"))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancelled())


def test_unconfigured_never_calls_network(monkeypatch) -> None:
    def unexpected(**kwargs):
        raise AssertionError("network must not run")

    monkeypatch.setattr(httpx, "AsyncClient", unexpected)
    with pytest.raises(KGError) as failure:
        asyncio.run(CompatibleModel(ModelEndpoint("", "", "")).chat("a", "b"))
    assert failure.value.code.value == "KG.LLM_NOT_CONFIGURED"


def test_compression_rejected_before_body_iteration(monkeypatch) -> None:
    class Compressed(httpx.AsyncByteStream):
        reads = 0

        async def __aiter__(self):
            self.reads += 1
            yield gzip.compress(b"x" * 16_000_000)

    body = Compressed()
    model = client(
        monkeypatch,
        lambda _: httpx.Response(
            200, headers={"Content-Encoding": "gzip"}, stream=body
        ),
    )
    with pytest.raises(KGError) as failure:
        asyncio.run(model.chat("a", "b"))
    assert failure.value.params["reason"] == "compressed_response_not_supported"
    assert body.reads == 0


def test_subnormal_embedding_is_a_unit_vector(monkeypatch) -> None:
    model = client(
        monkeypatch,
        lambda _: httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [5e-324, 5e-324]}]}
        ),
    )
    vector = asyncio.run(model.embed(["a"]))[0]
    assert math.hypot(*vector) == pytest.approx(1)
    assert vector[0] == pytest.approx(math.sqrt(0.5))


def test_excessive_json_nesting_is_structured_error(monkeypatch) -> None:
    content = '{"data":' + "[" * 10000 + "0" + "]" * 10000 + "}"
    model = client(monkeypatch, lambda _: httpx.Response(200, content=content))
    with pytest.raises(KGError) as failure:
        asyncio.run(model.embed(["a"]))
    assert failure.value.code.value == "KG.LLM_RESPONSE_INVALID"
