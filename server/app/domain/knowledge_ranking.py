"""Deterministic, storage-independent ranking for bounded knowledge retrieval."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence

from app.core.error_codes import ErrorCode
from app.core.errors import KGError
from app.core.vector_math import normalized_vector

RANKING_VERSION = "bm25-rrf-v1"
RRF_K = 60


def tokens(text: str) -> list[str]:
    """Latin words and Han bigrams; no language model or guessed translation."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    result: list[str] = []
    for part in re.findall(r"[\u3400-\u9fff]+|[^\W_\u3400-\u9fff]+", normalized):
        if re.fullmatch(r"[\u3400-\u9fff]+", part):
            result.extend(
                part[index : index + 2] for index in range(max(1, len(part) - 1))
            )
        else:
            result.append(part)
    return result


def keyword_scores(query: str, documents: dict[str, str]) -> dict[str, float]:
    """BM25 over the authorized active corpus supplied by the caller."""
    terms = set(tokens(query))
    if not terms or not documents:
        return {}
    counts = {key: Counter(tokens(value)) for key, value in documents.items()}
    lengths = {key: sum(value.values()) for key, value in counts.items()}
    average = sum(lengths.values()) / len(counts) or 1
    frequency = Counter(
        term for value in counts.values() for term in terms & value.keys()
    )
    scores: dict[str, float] = {}
    for key, value in counts.items():
        contributions: list[float] = []
        for term in sorted(terms):
            tf = value[term]
            if not tf:
                continue
            idf = math.log(
                1 + (len(counts) - frequency[term] + 0.5) / (frequency[term] + 0.5)
            )
            contributions.append(
                idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * lengths[key] / average))
            )
        score = math.fsum(contributions)
        if score:
            scores[key] = score
    return scores


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """Fail closed on corrupt vectors instead of masking index failures as no match."""
    if len(left) != len(right):
        raise KGError(ErrorCode.INVALID_REQUEST, {"reason": "invalid_embedding"})
    try:
        a_values, b_values = normalized_vector(left), normalized_vector(right)
    except (ValueError, OverflowError) as exc:
        raise KGError(
            ErrorCode.INVALID_REQUEST, {"reason": "invalid_embedding"}
        ) from exc
    return max(
        -1.0,
        min(
            1.0,
            math.fsum(a * b for a, b in zip(a_values, b_values, strict=True)),
        ),
    )


def ordered(scores: dict[str, float]) -> list[str]:
    return sorted(scores, key=lambda key: (-scores[key], key))


def reciprocal_rank_fusion(*rankings: dict[str, float]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for position, key in enumerate(ordered(ranking), start=1):
            scores[key] = scores.get(key, 0.0) + 1 / (RRF_K + position)
    return scores
