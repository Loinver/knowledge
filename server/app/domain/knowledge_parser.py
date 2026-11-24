"""Pure, bounded UTF-8 ingestion; no storage, model calls or process-global settings.

Evidence offsets are Python character indexes into ``normalized_text`` (NFC,
UTF-8 BOM removed, CRLF/CR converted to LF), not byte indexes into the upload.
Every segment/chunk text is an exact slice of that source. CSV text retains its
quoting/delimiters; ``cells`` contains decoded values. No header is inferred.
Markdown is retained as source, with ATX headings used only for section metadata.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from array import array
from bisect import bisect_right
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from app.core.errors import ErrorCode, KGError

PARSER_VERSION = "knowledge-parser-v1"
CHUNKER_VERSION = "knowledge-chunker-v1"
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_FILENAME_BYTES = 255
MAX_CHUNK_CHARS = 800
CHUNK_OVERLAP_CHARS = 80
MAX_CHUNKS = 2000
MAX_CSV_FIELD_CHARS = 65_536
MAX_CSV_ROW_CHARS = 262_144
MAX_CSV_COLUMNS = 256
MAX_CSV_ROWS = 20_000

_MEDIA_TYPES = {"txt": "text/plain", "md": "text/markdown", "csv": "text/csv"}
_COMPATIBLE_MIME = {
    "txt": {"text/plain", "application/octet-stream"},
    "md": {
        "text/plain",
        "text/markdown",
        "text/x-markdown",
        "application/octet-stream",
    },
    "csv": {"text/plain", "text/csv", "application/csv", "application/octet-stream"},
}
_HEADING = re.compile(r" {0,3}(#{1,6})[\t ]+(.+?)\s*$")
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)$")
_MIME_PARAMETER = re.compile(
    r"([a-z0-9!#$%&\'*+.^_`|~-]+)\s*=\s*"
    r'(?:"([^"\r\n]*)"|([a-z0-9!#$%&\'*+.^_`|~-]+))'
)


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Half-open character range; inclusive 1-based lines and paragraph/CSV row.

    CSV row numbers count logical records, including empty records; quoted
    newlines do not start a new record. Paragraph numbers include headings.
    """

    start_offset: int
    end_offset: int
    start_line: int
    end_line: int
    paragraph_number: int | None = None
    row_number: int | None = None


@dataclass(frozen=True, slots=True)
class DocumentSegment:
    id: str
    kind: Literal["paragraph", "heading", "row"]
    text: str
    location: SourceLocation
    section: str | None = None
    cells: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    id: str
    segment_id: str
    text: str
    location: SourceLocation
    section: str | None = None


@dataclass(frozen=True, slots=True)
class ParseWarning:
    reason: str
    location: SourceLocation
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    id: str
    filename: str
    media_type: str
    content_hash: str
    normalized_text: str
    parser_version: str
    chunker_version: str
    segments: tuple[DocumentSegment, ...]
    chunks: tuple[DocumentChunk, ...]
    warnings: tuple[ParseWarning, ...]
    partial: bool


@dataclass(frozen=True, slots=True)
class _Span:
    start: int
    end: int
    kind: Literal["paragraph", "heading", "row"]
    number: int
    section: str | None = None
    cells: tuple[str, ...] = ()


class _CsvParseError(Exception):
    def __init__(
        self, reason: str, start: int, end: int, row: int, limit: int | None = None
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.start = start
        self.end = end
        self.row = row
        self.limit = limit


def _invalid(reason: str, **params: object) -> KGError:
    return KGError(ErrorCode.INVALID_REQUEST, {"reason": reason, **params})


def _filename_and_type(filename: str, content_type: str | None) -> tuple[str, str]:
    # Treat both path syntaxes as untrusted display metadata, never as a path.
    name = unicodedata.normalize("NFC", filename.replace("\\", "/").rsplit("/", 1)[-1])
    name = "".join(
        "_" if unicodedata.category(char).startswith("C") or char in ':*?"<>|' else char
        for char in name
    ).strip(" .")
    if not name or "." not in name or not name.rsplit(".", 1)[0]:
        raise _invalid("knowledge_invalid_filename")
    if len(name.encode("utf-8")) > MAX_FILENAME_BYTES:
        raise _invalid("knowledge_filename_too_long", limit=MAX_FILENAME_BYTES)
    extension = name.rsplit(".", 1)[1].lower()
    if extension not in _MEDIA_TYPES:
        raise _invalid("knowledge_unsupported_extension")
    if content_type is not None:
        parts = content_type.lower().split(";")
        if parts[0].strip() not in _COMPATIBLE_MIME[extension]:
            raise _invalid("knowledge_mime_mismatch")
        for parameter in parts[1:]:
            match = _MIME_PARAMETER.fullmatch(parameter.strip())
            if match is None:
                raise _invalid("knowledge_mime_mismatch")
            value = match[2] if match[2] is not None else match[3]
            if match[1] == "charset" and value not in {
                "utf-8",
                "utf8",
            }:
                raise _invalid("knowledge_unsupported_charset")
    return name, extension


def validate_knowledge_upload(
    content: bytes, *, filename: str, content_type: str | None = None
) -> tuple[str, str]:
    """Validate upload metadata before queueing; parsing failures belong to tasks."""
    name, extension = _filename_and_type(filename, content_type)
    if len(content) > MAX_FILE_BYTES:
        raise _invalid("knowledge_file_too_large", limit=MAX_FILE_BYTES)
    if not content:
        raise _invalid("knowledge_empty_file")
    return name, _MEDIA_TYPES[extension]


def _normalize(content: bytes) -> str:
    if len(content) > MAX_FILE_BYTES:
        raise _invalid("knowledge_file_too_large", limit=MAX_FILE_BYTES)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _invalid("knowledge_invalid_utf8") from exc
    if any(
        (ord(char) < 32 and char not in "\t\n\r") or 127 <= ord(char) <= 159
        for char in text
    ) or text.startswith("%PDF-"):
        raise _invalid("knowledge_binary_content")
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    if not text.strip():
        raise _invalid("knowledge_empty_file")
    return text


def _hash(*parts: str) -> str:
    # Length-prefix each input so arbitrary source text cannot collide by framing.
    digest = hashlib.sha256()
    for part in parts:
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _location(
    lines: Sequence[int],
    start: int,
    end: int,
    *,
    paragraph: int | None = None,
    row: int | None = None,
) -> SourceLocation:
    return SourceLocation(
        start,
        end,
        bisect_right(lines, start),
        bisect_right(lines, max(start, end - 1)),
        paragraph,
        row,
    )


def _paragraphs(text: str, markdown: bool) -> Iterator[_Span]:
    start: int | None = None
    end = 0
    number = 0
    section: str | None = None
    fence: str | None = None
    for match in re.finditer(r"[^\n]+|\n", text):
        line = match.group()
        if line == "\n":
            continue
        # A gap of two newlines (or a whitespace-only line) ends a paragraph.
        heading = _HEADING.fullmatch(line) if markdown and fence is None else None
        blank = not line.strip()
        separated = start is not None and "\n\n" in text[end : match.start()]
        if start is not None and (blank or separated or heading):
            number += 1
            yield _Span(start, end, "paragraph", number, section)
            start = None
        if blank:
            continue
        if heading:
            section = re.sub(r"[\t ]+#+[\t ]*$", "", heading[2]).strip()
            number += 1
            yield _Span(match.start(), match.end(), "heading", number, section)
            continue
        if markdown and (marker := _FENCE.fullmatch(line)):
            if fence is None:
                fence = marker[1]
            elif (
                marker[1][0] == fence[0]
                and len(marker[1]) >= len(fence)
                and not marker[2].strip()
            ):
                fence = None
        if start is None:
            start = match.start() + len(line) - len(line.lstrip())
        end = match.start() + len(line.rstrip())
    if start is not None:
        number += 1
        yield _Span(start, end, "paragraph", number, section)


def _csv_record(text: str, start: int, row: int) -> tuple[_Span, int]:
    """Read one strict comma/double-quote record without csv's global field limit."""
    cells: list[str] = []
    field: list[str] = []
    state: Literal["start", "bare", "quoted", "closed"] = "start"
    position = start
    while position < len(text):
        char = text[position]
        if char == "\n" and state != "quoted":
            break
        if position - start >= MAX_CSV_ROW_CHARS:
            raise _CsvParseError(
                "knowledge_csv_row_too_large",
                start,
                position + 1,
                row,
                MAX_CSV_ROW_CHARS,
            )
        if state == "quoted":
            if char == '"':
                state = "closed"
            else:
                field.append(char)
        elif char == '"' and state in {"start", "closed"}:
            if state == "closed":
                field.append('"')
            state = "quoted"
        elif char == ",":
            cells.append("".join(field))
            field = []
            state = "start"
            if len(cells) >= MAX_CSV_COLUMNS:
                raise _CsvParseError(
                    "knowledge_csv_too_many_columns",
                    start,
                    position + 1,
                    row,
                    MAX_CSV_COLUMNS,
                )
        elif state == "closed" or char == '"':
            raise _CsvParseError("knowledge_csv_malformed", start, position + 1, row)
        else:
            field.append(char)
            state = "bare"
        if len(field) > MAX_CSV_FIELD_CHARS:
            raise _CsvParseError(
                "knowledge_csv_field_too_large",
                start,
                position + 1,
                row,
                MAX_CSV_FIELD_CHARS,
            )
        position += 1
    if state == "quoted":
        raise _CsvParseError("knowledge_csv_malformed", start, position, row)
    cells.append("".join(field))
    return _Span(start, position, "row", row, cells=tuple(cells)), position + 1


def _csv_rows(text: str) -> Iterator[_Span]:
    start = 0
    row = 0
    while start < len(text):
        row += 1
        if row > MAX_CSV_ROWS:
            raise _CsvParseError(
                "knowledge_csv_too_many_rows", start, start, row, MAX_CSV_ROWS
            )
        span, start = _csv_record(text, start, row)
        if any(cell.strip() for cell in span.cells):
            yield span


def _chunks(
    segment: DocumentSegment, lines: Sequence[int], text: str
) -> Iterator[DocumentChunk]:
    start = segment.location.start_offset
    stop = segment.location.end_offset
    while start < stop:
        end = min(start + MAX_CHUNK_CHARS, stop)
        if end < stop:
            # Prefer a nearby word/line boundary; still advance by at least 560.
            floor = end - 160
            boundary = max(text.rfind(" ", floor, end), text.rfind("\n", floor, end))
            if boundary >= floor:
                end = boundary + 1
        if text[start:end].strip():
            yield DocumentChunk(
                id=_hash(CHUNKER_VERSION, segment.id, str(start), str(end)),
                segment_id=segment.id,
                text=text[start:end],
                location=_location(
                    lines,
                    start,
                    end,
                    paragraph=segment.location.paragraph_number,
                    row=segment.location.row_number,
                ),
                section=segment.section,
            )
        if end == stop:
            break
        start = end - CHUNK_OVERLAP_CHARS


def parse_knowledge_file(
    content: bytes, *, filename: str, content_type: str | None = None
) -> ParsedDocument:
    """Parse and chunk atomically; invalid inputs raise KG.INVALID_REQUEST.

    Missing MIME is inferred. Generic octet-stream is accepted only alongside an
    allowed extension and valid UTF-8 text. IDs depend on normalized content,
    format, versions and source ranges, never on filename or wall-clock time.
    Any chunk overflow fails the entire parse. A CSV syntax/resource failure may
    retain preceding nonempty, complete rows; warnings identify the rejected row.
    """
    name, extension = _filename_and_type(filename, content_type)
    text = _normalize(content)
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    document_id = _hash(PARSER_VERSION, extension, content_hash)
    # Compact storage even for millions of empty physical lines in a 2 MiB file.
    lines = array("I", [0])
    lines.extend(match.end() for match in re.finditer("\n", text))
    segments: list[DocumentSegment] = []
    chunks: list[DocumentChunk] = []
    warnings: list[ParseWarning] = []
    spans = (
        _csv_rows(text) if extension == "csv" else _paragraphs(text, extension == "md")
    )
    try:
        for span in spans:
            segment = DocumentSegment(
                id=_hash(document_id, span.kind, str(span.start), str(span.end)),
                kind=span.kind,
                text=text[span.start : span.end],
                location=_location(
                    lines,
                    span.start,
                    span.end,
                    row=span.number if span.kind == "row" else None,
                    paragraph=span.number if span.kind != "row" else None,
                ),
                section=span.section,
                cells=span.cells,
            )
            segments.append(segment)
            for chunk in _chunks(segment, lines, text):
                if len(chunks) >= MAX_CHUNKS:
                    raise _invalid("knowledge_too_many_chunks", limit=MAX_CHUNKS)
                chunks.append(chunk)
    except _CsvParseError as exc:
        location = _location(lines, exc.start, exc.end, row=exc.row)
        if not chunks:
            params: dict[str, object] = {
                "row_number": exc.row,
                "line_number": location.start_line,
                "offset": exc.start,
            }
            if exc.limit is not None:
                params["limit"] = exc.limit
            raise _invalid(exc.reason, **params) from exc
        warnings.append(ParseWarning(exc.reason, location, exc.limit))
    if not chunks:
        raise _invalid("knowledge_empty_file")
    return ParsedDocument(
        id=document_id,
        filename=name,
        media_type=_MEDIA_TYPES[extension],
        content_hash=content_hash,
        normalized_text=text,
        parser_version=PARSER_VERSION,
        chunker_version=CHUNKER_VERSION,
        segments=tuple(segments),
        chunks=tuple(chunks),
        warnings=tuple(warnings),
        partial=bool(warnings),
    )
