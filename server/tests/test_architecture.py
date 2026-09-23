"""可执行的后端依赖方向约定；不导入应用或连接数据库。"""

from __future__ import annotations

import ast
import subprocess
import sys
from importlib.util import resolve_name
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
FORBIDDEN = {
    "core": ("app.api", "app.domain", "app.schemas", "fastapi", "starlette"),
    "models": (
        "app.api",
        "app.domain",
        "app.schemas",
        "app.connectors",
        "app.semantics",
    ),
    "schemas": ("app.api", "app.domain", "app.core.db", "app.connectors"),
    "domain": (
        "app.api",
        "app.main",
        "fastapi",
        "starlette",
        "sqlalchemy.create_engine",
        "app.semantics.rdflib_backend",
        "app.semantics.RdflibBackend",
    ),
    "connectors": ("app.api", "app.domain", "app.models", "app.core.db"),
    "semantics": ("app.api", "app.domain", "app.core.db", "sqlalchemy"),
}


def violations(source: str, path: Path) -> list[str]:
    relative = path.relative_to(APP)
    layer = relative.parts[0]
    package = ".".join(("app", *relative.parts[:-1]))
    forbidden = FORBIDDEN.get(layer, ())
    if layer != "semantics":
        forbidden += ("rdflib", "pyshacl", "owlrl")
    errors: list[str] = []
    for node in ast.walk(ast.parse(source, filename=str(path))):
        targets: list[str] = []
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = resolve_name("." * node.level + module, package)
            targets = [f"{module}.{alias.name}" for alias in node.names]
        for target in targets:
            if any(
                target == prefix or target.startswith(f"{prefix}.")
                for prefix in forbidden
            ):
                errors.append(f"{node.lineno}: {layer} must not depend on {target}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            if not isinstance(owner, ast.Name) or owner.id != "session":
                continue
            if layer == "domain" and node.func.attr in {
                "commit",
                "begin",
                "begin_nested",
            }:
                errors.append(
                    f"{node.lineno}: transactions belong to the application boundary"
                )
            if layer == "api" and node.func.attr in {
                "get",
                "execute",
                "query",
                "scalar",
                "scalars",
            }:
                errors.append(
                    f"{node.lineno}: database queries belong to domain services"
                )
    return errors


@pytest.mark.parametrize(
    "path", sorted(APP.rglob("*.py")), ids=lambda path: str(path.relative_to(APP))
)
def test_backend_dependency_direction(path: Path) -> None:
    assert not (errors := violations(path.read_text(), path)), "\n".join(errors)


@pytest.mark.parametrize(
    ("module", "source"),
    [
        ("domain/example.py", "from fastapi import HTTPException"),
        ("domain/example.py", "from ..api.v1 import validation"),
        ("domain/example.py", "from sqlalchemy import create_engine as engine"),
        ("domain/example.py", "session.commit()"),
        ("api/v1/example.py", "session.get(Model, 1)"),
        ("models/example.py", "from app.domain import ontology_service"),
        ("semantics/example.py", "from sqlalchemy.orm import Session"),
        ("core/example.py", "from starlette.responses import Response"),
    ],
)
def test_boundary_guard_rejects_reverse_dependencies(module: str, source: str) -> None:
    assert violations(source, APP / module)


def test_domain_errors_import_without_web_framework() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from app.core.errors import KGError; "
            "assert not any(n.split('.')[0] in {'fastapi', 'starlette'} "
            "for n in sys.modules)",
        ],
        cwd=APP.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
