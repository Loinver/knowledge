from __future__ import annotations

import csv
import hashlib
import io
import random

import pytest
from app.core.errors import ErrorCode, KGError
from app.domain.knowledge_parser import (
    CHUNK_OVERLAP_CHARS,
    CHUNKER_VERSION,
    MAX_CHUNK_CHARS,
    MAX_CHUNKS,
    MAX_CSV_COLUMNS,
    MAX_CSV_FIELD_CHARS,
    MAX_CSV_ROW_CHARS,
    MAX_CSV_ROWS,
    MAX_FILE_BYTES,
    MAX_FILENAME_BYTES,
    PARSER_VERSION,
    ParsedDocument,
    SourceLocation,
    parse_knowledge_file,
)


def _assert_evidence(document: ParsedDocument) -> None:
    source = document.normalized_text
    by_id = {segment.id: segment for segment in document.segments}
    assert len(by_id) == len(document.segments)
    assert len({chunk.id for chunk in document.chunks}) == len(document.chunks)
    for item in (*document.segments, *document.chunks):
        location = item.location
        assert 0 <= location.start_offset < location.end_offset <= len(source)
        assert source[location.start_offset : location.end_offset] == item.text
        assert location.start_line == source[: location.start_offset].count("\n") + 1
        assert location.end_line == source[: location.end_offset - 1].count("\n") + 1
    for chunk in document.chunks:
        segment = by_id[chunk.segment_id]
        assert 0 < len(chunk.text) <= MAX_CHUNK_CHARS
        assert segment.location.start_offset <= chunk.location.start_offset
        assert chunk.location.end_offset <= segment.location.end_offset
        assert chunk.section == segment.section


def test_unicode_normalization_and_original_normalized_locations() -> None:
    raw = "\ufeffCafe\u0301\r\n你好🙂\r\n\r\n  第二段\r第三行  \r\n"
    document = parse_knowledge_file(raw.encode(), filename="notes.txt")

    assert document.normalized_text == "Café\n你好🙂\n\n  第二段\n第三行  \n"
    assert [segment.text for segment in document.segments] == [
        "Café\n你好🙂",
        "第二段\n第三行",
    ]
    assert document.segments[0].location == SourceLocation(0, 8, 1, 2, 1, None)
    assert document.segments[1].location == SourceLocation(12, 19, 4, 5, 2, None)
    assert not document.partial
    assert not document.warnings
    _assert_evidence(document)


def test_paragraphs_with_blank_lines_indentation_and_adjacent_sections() -> None:
    text = "\n  first  \nsecond\n \t\n\n# Alpha\nbody\n## Beta ##\nmore\n\n"
    document = parse_knowledge_file(text.encode(), filename="notes.md")

    assert [segment.text for segment in document.segments] == [
        "first  \nsecond",
        "# Alpha",
        "body",
        "## Beta ##",
        "more",
    ]
    assert [segment.section for segment in document.segments] == [
        None,
        "Alpha",
        "Alpha",
        "Beta",
        "Beta",
    ]
    assert [segment.location.paragraph_number for segment in document.segments] == [
        1,
        2,
        3,
        4,
        5,
    ]
    assert [segment.kind for segment in document.segments] == [
        "paragraph",
        "heading",
        "paragraph",
        "heading",
        "paragraph",
    ]
    _assert_evidence(document)


def test_markdown_code_fences_do_not_change_sections() -> None:
    text = "# Real\n\n```md\n# code\n\n## still code\n```\n\n# Next\ntext"
    document = parse_knowledge_file(text.encode(), filename="notes.md")
    assert [s.section for s in document.segments] == [
        "Real",
        "Real",
        "Real",
        "Next",
        "Next",
    ]
    assert [s.text for s in document.segments if s.kind == "heading"] == [
        "# Real",
        "# Next",
    ]
    _assert_evidence(document)


def test_txt_hash_characters_are_not_markdown_headings() -> None:
    document = parse_knowledge_file(b"# title\nbody", filename="notes.txt")
    assert len(document.segments) == 1
    assert document.segments[0].section is None
    assert document.segments[0].kind == "paragraph"


def test_reprocessing_and_equivalent_encodings_have_stable_ids() -> None:
    raw = "\ufeffCafe\u0301\r\n\r\n你好🙂".encode()
    first = parse_knowledge_file(raw, filename="folder/first.TXT")
    assert first == parse_knowledge_file(raw, filename="folder/first.TXT")
    equivalent = parse_knowledge_file(
        "Café\n\n你好🙂".encode(), filename="renamed.txt", content_type="text/plain"
    )
    assert first.id == equivalent.id
    assert first.segments == equivalent.segments
    assert first.chunks == equivalent.chunks
    assert (
        first.content_hash
        == hashlib.sha256(equivalent.normalized_text.encode()).hexdigest()
    )
    assert first.parser_version == PARSER_VERSION
    assert first.chunker_version == CHUNKER_VERSION
    assert parse_knowledge_file(raw, filename="notes.md").id != first.id
    assert parse_knowledge_file(b"changed", filename="notes.txt").id != first.id


def test_duplicate_paragraphs_have_distinct_ids_and_locations() -> None:
    document = parse_knowledge_file(b"same\n\nsame", filename="notes.txt")
    assert len({segment.id for segment in document.segments}) == 2
    assert len({chunk.id for chunk in document.chunks}) == 2
    _assert_evidence(document)


@pytest.mark.parametrize(
    "text", ["字🙂" * 5000, "word " * 2000, "a " + " " * 2000 + "z"]
)
def test_long_paragraphs_terminate_and_keep_source_coverage(text: str) -> None:
    document = parse_knowledge_file(text.encode(), filename="notes.txt")
    assert len(document.chunks) > 1
    _assert_evidence(document)
    covered = bytearray(len(document.normalized_text))
    for chunk in document.chunks:
        start, end = chunk.location.start_offset, chunk.location.end_offset
        covered[start:end] = b"\1" * (end - start)
    assert all(covered[i] for i, char in enumerate(text) if not char.isspace())
    for left, right in zip(document.chunks, document.chunks[1:], strict=False):
        assert right.location.start_offset > left.location.start_offset
        assert (
            left.location.end_offset - right.location.start_offset
            <= CHUNK_OVERLAP_CHARS
        )


def test_chunk_locations_update_lines_inside_long_paragraph() -> None:
    text = "\n".join(f"Line {number:04d}: 中文🙂" for number in range(300))
    document = parse_knowledge_file(text.encode(), filename="notes.txt")
    assert len(document.segments) == 1
    assert document.chunks[-1].location.end_line == 300
    assert document.chunks[1].location.start_line > 1
    _assert_evidence(document)


def test_csv_quotes_newlines_empty_records_and_evidence() -> None:
    text = '\ufeffname,value\r\n\r\n"Café","一\r\n二, ""quoted"""\r\nlast,tail'
    document = parse_knowledge_file(text.encode(), filename="rows.csv")
    assert [s.cells for s in document.segments] == [
        ("name", "value"),
        ("Café", '一\n二, "quoted"'),
        ("last", "tail"),
    ]
    assert [s.location.row_number for s in document.segments] == [1, 3, 4]
    assert [s.location.start_line for s in document.segments] == [1, 3, 5]
    assert document.segments[1].location.end_line == 4
    assert document.segments[1].text == '"Café","一\n二, ""quoted"""'
    assert all(s.location.paragraph_number is None for s in document.segments)
    assert not document.partial
    _assert_evidence(document)


def test_csv_ragged_rows_are_not_silently_padded_or_dropped() -> None:
    document = parse_knowledge_file(b"a,b,c\nx\ny,z,", filename="rows.csv")
    assert [s.cells for s in document.segments] == [
        ("a", "b", "c"),
        ("x",),
        ("y", "z", ""),
    ]
    assert not document.warnings


def test_csv_round_trips_seeded_quoted_records_without_global_csv_changes() -> None:
    rng = random.Random(42)
    rows = [
        ["row" + str(i)]
        + [
            "".join(rng.choices('abc,\n" 中🙂', k=rng.randrange(25)))
            for _ in range(rng.randrange(1, 5))
        ]
        for i in range(100)
    ]
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    previous_limit = csv.field_size_limit()
    try:
        csv.field_size_limit(1)
        document = parse_knowledge_file(output.getvalue().encode(), filename="rows.csv")
        assert csv.field_size_limit() == 1
    finally:
        csv.field_size_limit(previous_limit)
    assert [s.cells for s in document.segments] == [tuple(row) for row in rows]
    assert not document.partial
    _assert_evidence(document)


@pytest.mark.parametrize(
    "bad_row", ['"open\nunfinished', 'a,"closed"junk', 'bare"quote,b']
)
def test_csv_malformed_record_keeps_only_complete_previous_rows(bad_row: str) -> None:
    prefix = "name,value\nvalid,one\n"
    document = parse_knowledge_file((prefix + bad_row).encode(), filename="rows.csv")
    assert document.partial
    assert len(document.segments) == len(document.chunks) == 2
    assert len(document.warnings) == 1
    warning = document.warnings[0]
    assert warning.reason == "knowledge_csv_malformed"
    assert warning.location.row_number == warning.location.start_line == 3
    assert warning.location.start_offset == len(prefix)
    assert all(chunk.location.end_offset < len(prefix) for chunk in document.chunks)
    assert document.normalized_text == prefix + bad_row
    assert document == parse_knowledge_file(
        (prefix + bad_row).encode(), filename="rows.csv"
    )
    _assert_evidence(document)


@pytest.mark.parametrize("prefix", ["", "\n", ',""\n', " , \n"])
def test_csv_failure_without_retained_content_is_an_error(prefix: str) -> None:
    with pytest.raises(KGError) as caught:
        parse_knowledge_file((prefix + '"unfinished').encode(), filename="rows.csv")
    assert caught.value.code == ErrorCode.INVALID_REQUEST
    assert caught.value.params["reason"] == "knowledge_csv_malformed"


@pytest.mark.parametrize("data", [b",,\n", b'"",""', b" , \n\n"])
def test_empty_csv_cells_are_not_content(data: bytes) -> None:
    with pytest.raises(KGError) as caught:
        parse_knowledge_file(data, filename="rows.csv")
    assert caught.value.params["reason"] == "knowledge_empty_file"


@pytest.mark.parametrize(
    ("row", "reason", "limit"),
    [
        (
            "x" * (MAX_CSV_FIELD_CHARS + 1),
            "knowledge_csv_field_too_large",
            MAX_CSV_FIELD_CHARS,
        ),
        (
            ",".join(["x"] * (MAX_CSV_COLUMNS + 1)),
            "knowledge_csv_too_many_columns",
            MAX_CSV_COLUMNS,
        ),
        (
            ",".join(["x" * MAX_CSV_FIELD_CHARS] * 5),
            "knowledge_csv_row_too_large",
            MAX_CSV_ROW_CHARS,
        ),
    ],
)
def test_csv_pathological_limits_are_explicit_and_keep_complete_rows_only(
    row: str, reason: str, limit: int
) -> None:
    with pytest.raises(KGError) as caught:
        parse_knowledge_file(row.encode(), filename="rows.csv")
    assert caught.value.params["reason"] == reason
    assert caught.value.params["limit"] == limit
    partial = parse_knowledge_file(
        ("kept,row\n" + row + "\nlater,row").encode(), filename="rows.csv"
    )
    assert [s.cells for s in partial.segments] == [("kept", "row")]
    assert partial.partial
    assert partial.warnings[0].reason == reason
    assert partial.warnings[0].limit == limit


def test_csv_exact_field_and_column_limits_are_accepted() -> None:
    text = "x" * MAX_CSV_FIELD_CHARS + "," * (MAX_CSV_COLUMNS - 1)
    document = parse_knowledge_file(text.encode(), filename="rows.csv")
    assert not document.partial
    assert len(document.segments[0].cells) == MAX_CSV_COLUMNS
    assert len(document.segments[0].cells[0]) == MAX_CSV_FIELD_CHARS
    _assert_evidence(document)


def test_csv_record_limit_counts_empty_records_and_is_not_silent() -> None:
    text = "kept\n" + "\n" * (MAX_CSV_ROWS - 1)
    assert not parse_knowledge_file(text.encode(), filename="rows.csv").partial
    partial = parse_knowledge_file((text + "last").encode(), filename="rows.csv")
    assert partial.partial
    assert partial.warnings[0].reason == "knowledge_csv_too_many_rows"
    assert partial.warnings[0].location.row_number == MAX_CSV_ROWS + 1
    with pytest.raises(KGError) as caught:
        parse_knowledge_file(
            ("\n" * MAX_CSV_ROWS + "last").encode(), filename="rows.csv"
        )
    assert caught.value.params["reason"] == "knowledge_csv_too_many_rows"


@pytest.mark.parametrize("filename", ["notes.txt", "rows.csv"])
def test_chunk_count_limit_is_atomic_even_with_retained_content(filename: str) -> None:
    separator = "\n\n" if filename.endswith(".txt") else "\n"
    content = separator.join(["row"] * MAX_CHUNKS)
    assert (
        len(parse_knowledge_file(content.encode(), filename=filename).chunks)
        == MAX_CHUNKS
    )
    with pytest.raises(KGError) as caught:
        parse_knowledge_file(
            (content + separator + "overflow").encode(), filename=filename
        )
    assert caught.value.params == {
        "reason": "knowledge_too_many_chunks",
        "limit": MAX_CHUNKS,
    }


def test_single_long_paragraph_also_enforces_chunk_limit() -> None:
    content = b"x" * (
        (MAX_CHUNK_CHARS - CHUNK_OVERLAP_CHARS) * MAX_CHUNKS + MAX_CHUNK_CHARS
    )
    assert len(content) < MAX_FILE_BYTES
    with pytest.raises(KGError) as caught:
        parse_knowledge_file(content, filename="notes.txt")
    assert caught.value.params["reason"] == "knowledge_too_many_chunks"


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"", "knowledge_empty_file"),
        ("\ufeff \t\r\n\u2003".encode(), "knowledge_empty_file"),
        (b"\xff", "knowledge_invalid_utf8"),
        (b"valid\n\n\xf0\x9f", "knowledge_invalid_utf8"),
        (b"text\0hidden", "knowledge_binary_content"),
        (b"PK\x03\x04archive", "knowledge_binary_content"),
        (b"\x1b[0m", "knowledge_binary_content"),
        ("text\u0085binary".encode(), "knowledge_binary_content"),
        (b"%PDF-1.4\n1 0 obj", "knowledge_binary_content"),
        (b"\xff\xfea\x00", "knowledge_invalid_utf8"),
    ],
)
def test_empty_binary_and_invalid_utf8_are_rejected(
    content: bytes, reason: str
) -> None:
    with pytest.raises(KGError) as caught:
        parse_knowledge_file(content, filename="notes.txt")
    assert caught.value.code == ErrorCode.INVALID_REQUEST
    assert caught.value.params["reason"] == reason


def test_size_limit_is_bytes_including_bom_and_is_inclusive() -> None:
    content = b" " * (MAX_FILE_BYTES - 1) + b"x"
    document = parse_knowledge_file(content, filename="notes.txt")
    assert document.segments[0].location.start_offset == MAX_FILE_BYTES - 1
    with pytest.raises(KGError) as caught:
        parse_knowledge_file(content + b"x", filename="notes.txt")
    assert caught.value.params == {
        "reason": "knowledge_file_too_large",
        "limit": MAX_FILE_BYTES,
    }
    with pytest.raises(KGError) as caught:
        parse_knowledge_file(b"\xef\xbb\xbf" + content, filename="notes.txt")
    assert caught.value.params["reason"] == "knowledge_file_too_large"


@pytest.mark.parametrize(
    ("filename", "content_type", "media_type"),
    [
        ("file.txt", None, "text/plain"),
        ("file.TXT", 'Text/Plain; Charset="UTF-8"', "text/plain"),
        ("file.md", "text/markdown", "text/markdown"),
        ("file.md", "text/x-markdown", "text/markdown"),
        ("file.md", "text/plain", "text/markdown"),
        ("file.csv", "text/csv; charset=utf8; header=present", "text/csv"),
        ("file.csv", "application/csv", "text/csv"),
        ("file.csv", "text/plain", "text/csv"),
        ("file.txt", "application/octet-stream", "text/plain"),
    ],
)
def test_mime_compatible_allowlist(
    filename: str, content_type: str | None, media_type: str
) -> None:
    document = parse_knowledge_file(
        b"content", filename=filename, content_type=content_type
    )
    assert document.media_type == media_type


@pytest.mark.parametrize(
    ("filename", "content_type", "reason"),
    [
        ("file.pdf", "text/plain", "knowledge_unsupported_extension"),
        ("file.txt.exe", "text/plain", "knowledge_unsupported_extension"),
        ("file.txt", "text/csv", "knowledge_mime_mismatch"),
        ("file.txt", "text/html", "knowledge_mime_mismatch"),
        ("file.md", "application/json", "knowledge_mime_mismatch"),
        ("file.csv", "application/vnd.ms-excel", "knowledge_mime_mismatch"),
        ("file.csv", "", "knowledge_mime_mismatch"),
        ("file.csv", "text/csv; bad-parameter", "knowledge_mime_mismatch"),
        ("file.csv", 'text/csv; charset="utf-8', "knowledge_mime_mismatch"),
        ("file.csv", 'text/csv; charset=utf-8"', "knowledge_mime_mismatch"),
        ("file.txt", "text/plain; charset=latin1", "knowledge_unsupported_charset"),
    ],
)
def test_mime_and_extension_rejections(
    filename: str, content_type: str, reason: str
) -> None:
    with pytest.raises(KGError) as caught:
        parse_knowledge_file(b"content", filename=filename, content_type=content_type)
    assert caught.value.params["reason"] == reason


def test_filename_is_safe_basename_with_unicode_normalization() -> None:
    document = parse_knowledge_file(
        b"content", filename="C:\\fake\\../../other/  Cafe\u0301\x00\u202e?.TXT  "
    )
    assert document.filename == "Café___.TXT"
    assert "/" not in document.filename and "\\" not in document.filename


@pytest.mark.parametrize("filename", ["", "../", "..", ".", ".txt", "no-extension"])
def test_empty_or_invalid_filenames_are_rejected(filename: str) -> None:
    with pytest.raises(KGError) as caught:
        parse_knowledge_file(b"content", filename=filename)
    assert caught.value.params["reason"] == "knowledge_invalid_filename"


def test_filename_length_is_bounded_in_utf8_bytes_without_silent_truncation() -> None:
    name = "x" * (MAX_FILENAME_BYTES - 4) + ".txt"
    assert parse_knowledge_file(b"content", filename=name).filename == name
    for filename in ("x" + name, "文" * 84 + ".txt"):
        with pytest.raises(KGError) as caught:
            parse_knowledge_file(b"content", filename=filename)
        assert caught.value.params == {
            "reason": "knowledge_filename_too_long",
            "limit": MAX_FILENAME_BYTES,
        }
