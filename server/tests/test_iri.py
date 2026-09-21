from __future__ import annotations

import pytest
from app.iri import build_iri, is_valid_name, is_valid_namespace


def test_iri_is_namespace_plus_name() -> None:
    assert (
        build_iri("https://example.org/core#", "Employee")
        == "https://example.org/core#Employee"
    )


@pytest.mark.parametrize("name", ["Employee", "ProjectParticipation", "X1"])
def test_valid_names(name: str) -> None:
    assert is_valid_name(name)


@pytest.mark.parametrize(
    "name", ["employee", "project_participation", "1X", "", "Employee Role"]
)
def test_invalid_names(name: str) -> None:
    assert not is_valid_name(name)


@pytest.mark.parametrize(
    "namespace", ["https://example.org/core#", "http://example.org/std/"]
)
def test_valid_namespaces(namespace: str) -> None:
    assert is_valid_namespace(namespace)


def test_namespace_must_end_with_separator() -> None:
    assert not is_valid_namespace("https://example.org/core")


def test_invalid_input_raises_instead_of_silent_fix() -> None:
    with pytest.raises(ValueError):
        build_iri("https://example.org/core", "Employee")
    with pytest.raises(ValueError):
        build_iri("https://example.org/core#", "employee")
