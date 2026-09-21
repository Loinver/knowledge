"""语义适配层：RDF/SHACL/OWL 适配，可替换实现。"""

from __future__ import annotations

from app.semantics.backend import (
    PARSER_JSONLD,
    PARSER_TURTLE,
    SERIALIZER_JSONLD,
    SERIALIZER_TURTLE,
    ReasonReport,
    SemanticBackend,
    ValidationReport,
)
from app.semantics.rdflib_backend import RdflibBackend

__all__ = [
    "PARSER_JSONLD",
    "PARSER_TURTLE",
    "SERIALIZER_JSONLD",
    "SERIALIZER_TURTLE",
    "RdflibBackend",
    "ReasonReport",
    "SemanticBackend",
    "ValidationReport",
]
