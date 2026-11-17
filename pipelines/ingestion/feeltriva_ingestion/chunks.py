"""Narrative text files as searchable, pending knowledge chunks (M1.10).

Handoff rules applied here:

- `docs/04`: archive 13 text files -> `evidence_chunks`; "preserve text, URL, extraction
  version, character offsets and attribution". `category` is preserved but "not trusted as an
  approved taxonomy"; `word_count` is "a source attribute, not an evidence score".
- `docs/01` section 6: "chunk along clinical section boundaries ... text offsets ... maintain
  parent document links"; raw dataset text is kept apart from reviewed clinical references.
- `docs/05` M2: pending content can never enter clinical serving. Every chunk therefore belongs
  to a knowledge release whose status is `pending`.

Each file has a three-line header (Disease, Category, URL), a rule line, and a body with
wiki-style headings (`== Title ==`, `=== Subtitle ===`). A chunk is a run of whole paragraphs
inside one section. Offsets are character positions in the decoded file exactly as stored, so
`document[char_start:char_end] == chunk_text` always holds and the source can be re-read.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from feeltriva_api.settings import Settings
from sqlalchemy import create_engine

from .archives import RAW_DIR, Manifest, load_manifest, verify_all
from .cases import _raw_cursor
from .load import RELEASE_ID, disease_candidate_id, source_id

KNOWLEDGE_RELEASE_ID = "knowledge-import-0"
EXTRACTION_VERSION = "sections-1"
MAX_CHARS = 2000
TEXT_ARCHIVE = "archive(13).zip"
CATEGORY_FLAG = "source_category_unreviewed"
# Sections that are reference lists or navigation, not prose about the condition.
BOILERPLATE = {
    "references",
    "external links",
    "see also",
    "notes",
    "further reading",
    "bibliography",
    "citations",
    "sources",
    "footnotes",
    "explanatory notes",
    "works cited",
}

_HEADER = re.compile(
    r"\ADisease : (?P<disease>.*?)\r?\nCategory: (?P<category>.*?)\r?\nURL     : (?P<url>.*?)\r?\n=+\r?\n"
)
_HEADING = re.compile(r"^(={2,})[ \t]*(.+?)[ \t]*\1[ \t]*\r?$", re.M)
_PARAGRAPH_BREAK = re.compile(r"(?:\r?\n[ \t]*){2,}")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class ChunkingError(ValueError):
    pass


@dataclass(frozen=True)
class Chunk:
    start: int
    end: int
    text: str
    section_path: tuple[str, ...]
    section_level: int
    boilerplate: bool


@dataclass(frozen=True)
class Document:
    disease: str
    category: str
    url: str
    body_start: int
    word_count: int
    chunks: tuple[Chunk, ...]


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _split_long(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """A paragraph longer than MAX_CHARS is cut at sentence ends (or hard at the limit)."""
    pieces = []
    while end - start > MAX_CHARS:
        window = text[start : start + MAX_CHARS]
        cuts = [m.start() for m in _SENTENCE_END.finditer(window)]
        cut = start + (cuts[-1] if cuts else MAX_CHARS)
        pieces.append(_trim(text, start, cut))
        start = _trim(text, cut, end)[0]
    pieces.append((start, end))
    return [p for p in pieces if p[1] > p[0]]


def _paragraphs(text: str, start: int, end: int) -> list[tuple[int, int]]:
    spans = []
    position = start
    for match in _PARAGRAPH_BREAK.finditer(text, start, end):
        spans.append(_trim(text, position, match.start()))
        position = match.end()
    spans.append(_trim(text, position, end))
    return [s for s in spans if s[1] > s[0]]


def chunk_document(text: str) -> Document:
    """Split one narrative file into section-bounded chunks with exact character offsets."""
    header = _HEADER.match(text)
    if header is None:
        raise ChunkingError("file does not start with the Disease / Category / URL header")
    body_start = header.end()
    headings = list(_HEADING.finditer(text, body_start))
    # (level, title, content_start, content_end); the lead before the first heading is level 1.
    sections: list[tuple[int, str, int, int]] = [(1, "", body_start, headings[0].start() if headings else len(text))]
    for index, heading in enumerate(headings):
        content_end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        sections.append((len(heading.group(1)), heading.group(2).strip(), heading.end(), content_end))

    chunks: list[Chunk] = []
    path: list[tuple[int, str]] = []
    for level, title, start, end in sections:
        if title:
            path = [(lv, t) for lv, t in path if lv < level] + [(level, title)]
        titles = tuple(t for _, t in path)
        boilerplate = any(t.lower() in BOILERPLATE for t in titles)
        current: tuple[int, int] | None = None
        for p_start, p_end in _paragraphs(text, start, end):
            for piece in _split_long(text, p_start, p_end):
                if current is not None and piece[1] - current[0] <= MAX_CHARS:
                    current = (current[0], piece[1])  # paragraphs of one section share a chunk
                    continue
                if current is not None:
                    chunks.append(Chunk(*current, text[current[0] : current[1]], titles, level, boilerplate))
                current = piece
        if current is not None:
            chunks.append(Chunk(*current, text[current[0] : current[1]], titles, level, boilerplate))
    return Document(
        header["disease"].strip(),
        header["category"].strip(),
        header["url"].strip(),
        body_start,
        len(text[body_start:].split()),
        tuple(chunks),
    )


def uncovered_characters(text: str, document: Document) -> int:
    """Non-whitespace body characters that are in neither a chunk nor a heading line. Must be 0."""
    covered = [False] * len(text)
    for chunk in document.chunks:
        for i in range(chunk.start, chunk.end):
            if covered[i]:
                raise ChunkingError("chunks overlap")
            covered[i] = True
    for heading in _HEADING.finditer(text, document.body_start):
        for i in range(heading.start(), heading.end()):
            covered[i] = True
    return sum(1 for i in range(document.body_start, len(text)) if not covered[i] and not text[i].isspace())


def load_chunks(
    raw_dir: Path = RAW_DIR,
    database_url: str | None = None,
    manifest: Manifest | None = None,
    archive: str = TEXT_ARCHIVE,
) -> dict[str, Any]:
    """Chunk the narrative files of `archive` (the 85 archive-13 texts) into `evidence_chunks`
    under a pending knowledge release."""
    if database_url is None:
        settings = Settings()
        database_url = settings.migration_database_url or settings.database_url
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL (or DATABASE_URL) is required")
    manifest = manifest or load_manifest()
    verify_all(raw_dir, manifest)
    files = [t for t in manifest.text_files if t["archive"] == archive]
    text_source = source_id(archive, "*.txt")
    main_source = source_id(archive, "diseases_main.csv")
    totals: dict[str, Any] = {
        "files": 0,
        "chunks": 0,
        "chunks_inserted": 0,
        "boilerplate_chunks": 0,
        "characters_in_chunks": 0,
        "uncovered_characters": 0,
        "header_mismatches": [],
        "word_count_mismatches": [],
        "digest_mismatches": [],
        "longest_chunk": 0,
    }
    engine = create_engine(database_url)
    with zipfile.ZipFile(raw_dir / archive) as z, _raw_cursor(engine) as cur:
        main = {
            row["name"]: row
            for row in csv.DictReader(io.TextIOWrapper(z.open("diseases_main.csv"), encoding="utf-8-sig"))
        }
        cur.execute("SELECT file_path, record_id FROM source_records WHERE source_id = %s", (text_source,))
        records = dict(cur.fetchall())
        if len(records) != len(files):
            raise SystemExit(f"{len(records)} text-file records found, {len(files)} expected; run `load` first")
        cur.execute(
            """INSERT INTO knowledge_releases (release_id, mapping_release_id, version, manifest_uri, status)
               VALUES (%s, %s, 'import-0', 'repo://specs/ingestion_manifest.json#text_files', 'pending')
               ON CONFLICT DO NOTHING""",
            (KNOWLEDGE_RELEASE_ID, RELEASE_ID),
        )
        for entry in files:
            name = entry["file"]
            raw = z.read(name)
            digest = hashlib.sha256(raw).hexdigest()
            if digest != entry["sha256"]:
                totals["digest_mismatches"].append(name)
                continue
            text = raw.decode("utf-8")
            document = chunk_document(text)
            row = main.get(document.disease)
            if row is None or row["category"] != document.category or row["url"] != document.url:
                totals["header_mismatches"].append(name)
            declared = int(row["word_count"]) if row and row["word_count"].isdigit() else None
            if declared != document.word_count:
                totals["word_count_mismatches"].append(name)
            totals["files"] += 1
            totals["uncovered_characters"] += uncovered_characters(text, document)
            record_id = records[name]
            for index, chunk in enumerate(document.chunks):
                chunk_id = (
                    "chk_"
                    + hashlib.sha256(
                        "\x1f".join((record_id, EXTRACTION_VERSION, str(chunk.start), str(chunk.end))).encode()
                    ).hexdigest()[:24]
                )
                metadata = {
                    "archive": archive,
                    "file": name,
                    "document_sha256": digest,
                    "extraction_version": EXTRACTION_VERSION,
                    "chunk_index": index,
                    "char_start": chunk.start,
                    "char_end": chunk.end,
                    "section_path": list(chunk.section_path),
                    "section_level": chunk.section_level,
                    "boilerplate": chunk.boilerplate,
                    "disease_label": document.disease,
                    "disease_id": disease_candidate_id(document.disease),
                    "native_id": row["id"] if row else None,
                    "source_url": document.url,
                    # Preserved as supplied; not an approved taxonomy (e.g. asthma is labelled Mental Health).
                    "source_category_unreviewed": document.category,
                    "word_count_declared": declared,
                    "word_count_measured": document.word_count,
                }
                cur.execute(
                    """INSERT INTO evidence_chunks (chunk_id, record_id, knowledge_release_id, chunk_text,
                                                    search_vector, metadata)
                       VALUES (%s, %s, %s, %s, to_tsvector('english', %s), %s::jsonb) ON CONFLICT DO NOTHING""",
                    (chunk_id, record_id, KNOWLEDGE_RELEASE_ID, chunk.text, chunk.text, json.dumps(metadata)),
                )
                totals["chunks_inserted"] += cur.rowcount
                totals["chunks"] += 1
                totals["boilerplate_chunks"] += chunk.boilerplate
                totals["characters_in_chunks"] += len(chunk.text)
                totals["longest_chunk"] = max(totals["longest_chunk"], len(chunk.text))
        # The disease table's own category and word count stay with its rows: the category is
        # queued for review, the word count is recorded beside the description statement.
        cur.execute(
            """UPDATE source_records SET quality_flags = quality_flags || %s::jsonb
               WHERE source_id = %s AND NOT quality_flags @> %s::jsonb""",
            (json.dumps([CATEGORY_FLAG]), main_source, json.dumps([CATEGORY_FLAG])),
        )
        totals["category_flags_added"] = cur.rowcount
        added = 0
        for row in main.values():
            cur.execute(
                """UPDATE statement_sources ss SET text_span = ss.text_span || %s::jsonb
                   FROM source_records r
                   WHERE ss.record_id = r.record_id AND r.source_id = %s
                     AND ss.text_span ->> 'native_id' = %s AND NOT ss.text_span ? 'word_count'""",
                (json.dumps({"word_count": int(row["word_count"])}), main_source, row["id"]),
            )
            added += cur.rowcount
        totals["word_counts_recorded"] = added
        cur.execute(
            """SELECT count(*), count(DISTINCT record_id), count(*) FILTER (WHERE search_vector IS NOT NULL),
                      (SELECT status FROM knowledge_releases WHERE release_id = %s)
               FROM evidence_chunks WHERE knowledge_release_id = %s AND record_id = ANY(%s)""",
            (KNOWLEDGE_RELEASE_ID, KNOWLEDGE_RELEASE_ID, list(records.values())),
        )
        stored = cur.fetchone()
        totals["stored"] = {
            "chunks": stored[0],
            "documents": stored[1],
            "with_search_vector": stored[2],
            "release_status": stored[3],
        }
    engine.dispose()
    return totals


def check(totals: dict[str, Any], expected_files: int) -> list[str]:
    diffs = []
    if totals["files"] != expected_files:
        diffs.append(f"{totals['files']} files chunked, {expected_files} expected")
    for key in ("digest_mismatches", "header_mismatches", "word_count_mismatches"):
        if totals[key]:
            diffs.append(f"{key}: {totals[key][:5]}")
    if totals["uncovered_characters"]:
        diffs.append(f"{totals['uncovered_characters']} body characters are in no chunk")
    stored = totals["stored"]
    if stored["chunks"] != totals["chunks"] or stored["with_search_vector"] != totals["chunks"]:
        diffs.append(f"stored {stored} but {totals['chunks']} chunks were produced")
    if stored["documents"] != expected_files:
        diffs.append(f"chunks cover {stored['documents']} documents, {expected_files} expected")
    if stored["release_status"] != "pending":
        diffs.append(f"knowledge release is {stored['release_status']!r}; imported text must stay pending")
    return diffs


def search_chunks(
    database_url: str | None, query: str, limit: int = 5, include_boilerplate: bool = False
) -> list[dict[str, Any]]:
    """Full-text search for reviewers and developers. It reads pending content on purpose and
    must never be used to serve users: serving reads approved releases only."""
    if database_url is None:
        settings = Settings()
        database_url = settings.migration_database_url or settings.database_url
    engine = create_engine(database_url or "")
    with _raw_cursor(engine) as cur:
        cur.execute(
            """SELECT c.chunk_id, c.metadata ->> 'disease_label', c.metadata -> 'section_path',
                      (c.metadata ->> 'char_start')::int, (c.metadata ->> 'char_end')::int,
                      r.status, round(ts_rank(c.search_vector, q)::numeric, 4),
                      ts_headline('english', c.chunk_text, q, 'MaxWords=24, MinWords=10, MaxFragments=1')
               FROM evidence_chunks c
               JOIN knowledge_releases r ON r.release_id = c.knowledge_release_id,
                    websearch_to_tsquery('english', %s) q
               WHERE c.search_vector @@ q AND (%s OR NOT (c.metadata ->> 'boilerplate')::boolean)
               ORDER BY ts_rank(c.search_vector, q) DESC, c.chunk_id LIMIT %s""",
            (query, include_boilerplate, max(1, min(limit, 50))),
        )
        keys = ("chunk_id", "disease", "section_path", "char_start", "char_end", "release_status", "rank", "snippet")
        rows = [dict(zip(keys, row, strict=True)) for row in cur.fetchall()]
    engine.dispose()
    return rows
