from __future__ import annotations

import math
import os
import subprocess
import sys

import pytest
from app.core.errors import KGError
from app.domain.knowledge_ranking import (
    cosine,
    keyword_scores,
    ordered,
    reciprocal_rank_fusion,
    tokens,
)


def test_keyword_ranks_chinese_and_latin_without_translating() -> None:
    corpus = {"a": "知识检索服务 Search", "b": "会议纪要 Meeting", "c": "检索"}
    scores = keyword_scores("知识检索 SEARCH", corpus)
    assert ordered(scores) == ["a", "c"]
    assert keyword_scores("不存在", corpus) == {}
    assert tokens("ＡＢＣ") == ["abc"]
    assert tokens("AI知识库V2") == ["ai", "知识", "识库", "v2"]


def test_ranking_is_stable_and_fusion_uses_both_lists() -> None:
    lexical = {"b": 2.0, "a": 2.0}
    semantic = {"c": 0.99, "b": 0.9}
    assert ordered(lexical) == ["a", "b"]
    fused = reciprocal_rank_fusion(lexical, semantic)
    assert ordered(fused) == ["b", "a", "c"]
    assert fused == reciprocal_rank_fusion(
        dict(reversed(list(lexical.items()))), semantic
    )


def test_cosine_and_invalid_index_vectors() -> None:
    assert cosine([1, 0], [1, 0]) == 1
    assert cosine([1, 0], [0, 1]) == 0
    assert cosine([1e200, 0], [1e200, 0]) == 1
    assert cosine([5e-324, 5e-324], [1, 0]) == pytest.approx(math.sqrt(0.5))
    for vector in ([], [0, 0], [1], [float("nan"), 1], [float("inf"), 0]):
        with pytest.raises(KGError):
            cosine([1, 0], vector)


def test_bm25_order_is_identical_across_hash_seeds() -> None:
    from pathlib import Path

    code = """from app.domain.knowledge_ranking import keyword_scores, ordered
query = ' '.join('word' + str(i) for i in range(10))
print(ordered(keyword_scores(query, {'a': query + ' word0', 'b': query + ' word9'})))
"""
    outputs = []
    for seed in ("6", "7", "19"):
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        )
        outputs.append(result.stdout)
    assert outputs == ["['a', 'b']\n"] * 3
