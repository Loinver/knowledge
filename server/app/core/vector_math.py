"""Numerically stable normalization shared by model validation and retrieval."""

from __future__ import annotations

import math
from collections.abc import Sequence


def normalized_vector(values: Sequence[float]) -> list[float]:
    if not values or not all(math.isfinite(value) for value in values):
        raise ValueError("invalid_vector")
    scale = max(abs(value) for value in values)
    if not scale:
        raise ValueError("zero_vector")
    scaled = [value / scale for value in values]
    norm = math.hypot(*scaled)
    return [value / norm for value in scaled]
