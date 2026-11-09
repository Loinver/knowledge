from __future__ import annotations

import asyncio
import json

import pytest
from app.core.errors import KGError
from app.domain.knowledge_answering import EvidencePassage, answer_from_evidence


class Model:
    def __init__(self, reply: dict) -> None:
        self.reply = reply
        self.calls = 0

    async def chat(self, system: str, user: str) -> str:
        self.calls += 1
        data = json.loads(user)
        assert [item["chunk_id"] for item in data["evidence"]] == ["public-1"]
        return json.dumps(self.reply)


EVIDENCE = [EvidencePassage("public-1", "设备维护周期为三个月，负责人是运营部门。")]


def test_answer_returns_only_exact_excerpts_not_generated_claims() -> None:
    model = Model(
        {
            "status": "ANSWERED",
            "answer": "unverified model claim must never escape",
            "citations": [{"chunk_id": "public-1", "quote": "设备维护周期为三个月"}],
        }
    )
    result = asyncio.run(answer_from_evidence(model, "维护周期？", EVIDENCE))
    assert result.status == "ANSWERED"
    assert result.citations[0].quote == "设备维护周期为三个月"
    assert not hasattr(result, "answer")


def test_no_evidence_does_not_call_model() -> None:
    model = Model({})
    result = asyncio.run(answer_from_evidence(model, "维护周期？", []))
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert model.calls == 0


@pytest.mark.parametrize(
    "citation",
    [
        {"chunk_id": "private-secret", "quote": "设备维护周期为三个月"},
        {"chunk_id": "public-1", "quote": "设备维护周期为十二个月"},
        {"chunk_id": "public-1", "quote": "设备"},
        {"chunk_id": ["public-1"], "quote": "设备维护周期为三个月"},
    ],
)
def test_unknown_or_invented_citations_fail_closed(citation) -> None:
    model = Model({"status": "ANSWERED", "citations": [citation]})
    with pytest.raises(KGError) as failure:
        asyncio.run(answer_from_evidence(model, "维护周期？", EVIDENCE))
    assert failure.value.code.value == "KG.LLM_RESPONSE_INVALID"


def test_insufficient_response_is_not_success() -> None:
    result = asyncio.run(
        answer_from_evidence(
            Model({"status": "INSUFFICIENT_EVIDENCE", "citations": []}),
            "没有证据的问题",
            EVIDENCE,
        )
    )
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.citations == ()


def test_invalid_status_type_is_a_structured_model_error() -> None:
    model = Model({"status": ["ANSWERED"], "citations": []})
    with pytest.raises(KGError) as failure:
        asyncio.run(answer_from_evidence(model, "维护周期？", EVIDENCE))
    assert failure.value.code.value == "KG.LLM_RESPONSE_INVALID"


def test_deeply_nested_answer_is_structured_error() -> None:
    class NestedModel:
        async def chat(self, system: str, user: str) -> str:
            return '{"citations":' + "[" * 10000 + "0" + "]" * 10000 + "}"

    with pytest.raises(KGError) as failure:
        asyncio.run(answer_from_evidence(NestedModel(), "周期？", EVIDENCE))
    assert failure.value.code.value == "KG.LLM_RESPONSE_INVALID"


def test_parse_rank_and_answer_preserve_original_source_offsets() -> None:
    from app.domain.knowledge_parser import parse_knowledge_file
    from app.domain.knowledge_ranking import keyword_scores, ordered

    document = parse_knowledge_file(
        "# 运维说明\r\n\r\n设备维护周期为三个月。\r\n\r\n会议每周召开。".encode(),
        filename="operations.md",
    )
    chunks = {chunk.id: chunk for chunk in document.chunks}
    scores = keyword_scores(
        "设备维护周期", {key: item.text for key, item in chunks.items()}
    )
    selected = chunks[ordered(scores)[0]]

    class SelectionModel:
        async def chat(self, system: str, user: str) -> str:
            source = json.loads(user)["evidence"][0]
            return json.dumps(
                {
                    "status": "ANSWERED",
                    "citations": [
                        {"chunk_id": source["chunk_id"], "quote": source["text"]}
                    ],
                }
            )

    answer = asyncio.run(
        answer_from_evidence(
            SelectionModel(),
            "设备维护周期？",
            [EvidencePassage(selected.id, selected.text)],
        )
    )
    citation = answer.citations[0]
    location = chunks[citation.chunk_id].location
    assert (
        document.normalized_text[location.start_offset : location.end_offset]
        == citation.quote
    )
    assert location.start_line == 3
