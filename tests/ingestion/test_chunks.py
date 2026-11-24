"""Chunking of narrative text files, and loading them as pending, searchable knowledge chunks."""

from __future__ import annotations

import hashlib
import os
import uuid
import zipfile

import pytest
from feeltriva_api.models import Source, SourceRecord
from feeltriva_ingestion.archives import RAW_DIR, Manifest, load_manifest, sha256_file
from feeltriva_ingestion.chunks import (
    KNOWLEDGE_RELEASE_ID,
    MAX_CHARS,
    ChunkingError,
    check,
    chunk_document,
    load_chunks,
    search_chunks,
    uncovered_characters,
)
from feeltriva_ingestion.load import source_id
from sqlalchemy import text

LONG = " ".join(f"Sentence number {i} about synthetic topic zeta." for i in range(120))  # one paragraph > MAX_CHARS
DOC = (
    "Disease : Synthetic Condition\r\nCategory: Sample Category\r\nURL     : https://example.org/synthetic\r\n"
    + "=" * 60
    + "\r\n\r\n"
    "Lead paragraph one about alphaword.\r\n\r\nLead paragraph two.\r\n\r\n\r\n"
    "== Signs and symptoms ==\r\n\r\nFirst symptom paragraph with betaword.\r\nSame paragraph, second line.\r\n\r\n"
    "=== Subsection ===\r\n\r\n" + LONG + "\r\n\r\n\r\n"
    "== Empty section ==\r\n\r\n\r\n"
    "== References ==\r\n\r\nA reference entry.\r\n"
)


def test_chunks_follow_sections_and_offsets_reproduce_the_text():
    document = chunk_document(DOC)
    assert (document.disease, document.category, document.url) == (
        "Synthetic Condition",
        "Sample Category",
        "https://example.org/synthetic",
    )
    assert document.word_count == len(DOC[document.body_start :].split())
    for chunk in document.chunks:
        assert DOC[chunk.start : chunk.end] == chunk.text  # exact offsets, CRLF included
        assert chunk.text == chunk.text.strip() and chunk.text  # no surrounding whitespace, never empty
        assert len(chunk.text) <= MAX_CHARS
    assert uncovered_characters(DOC, document) == 0  # nothing in the body is dropped
    starts = [c.start for c in document.chunks]
    assert starts == sorted(starts) and all(a.end <= b.start for a, b in zip(document.chunks, document.chunks[1:], strict=False))

    lead = document.chunks[0]
    assert lead.section_path == () and "alphaword" in lead.text and "Lead paragraph two." in lead.text
    assert "==" not in "".join(c.text for c in document.chunks)  # heading lines are metadata, not content
    symptoms = next(c for c in document.chunks if "betaword" in c.text)
    assert symptoms.section_path == ("Signs and symptoms",) and "second line" in symptoms.text
    sub = [c for c in document.chunks if c.section_path == ("Signs and symptoms", "Subsection")]
    assert len(sub) >= 2 and all(c.text.endswith(".") for c in sub)  # long paragraph cut at sentence ends
    assert " ".join(c.text for c in sub) == LONG
    assert not any(c.section_path == ("Empty section",) for c in document.chunks)
    reference = document.chunks[-1]
    assert reference.section_path == ("References",) and reference.boilerplate
    assert not symptoms.boilerplate and not lead.boilerplate


def test_a_sibling_heading_replaces_the_previous_one_in_the_path():
    doc = (
        "Disease : X\nCategory: C\nURL     : u\n=====\n\n"
        "== A ==\n\ntext a\n\n=== A1 ===\n\ntext a1\n\n== B ==\n\ntext b\n\n==== B deep ====\n\ntext deep\n"
    )
    paths = {c.text: c.section_path for c in chunk_document(doc).chunks}
    assert paths == {"text a": ("A",), "text a1": ("A", "A1"), "text b": ("B",), "text deep": ("B", "B deep")}


def test_file_without_the_expected_header_is_refused():
    with pytest.raises(ChunkingError, match="header"):
        chunk_document("Just some text\n\n== Heading ==\n\nbody\n")


@pytest.mark.archives
def test_every_real_file_is_fully_covered_with_exact_offsets():
    manifest = load_manifest()
    total = 0
    with zipfile.ZipFile(RAW_DIR / "archive(13).zip") as z:
        for entry in manifest.text_files:
            raw = z.read(entry["file"])
            assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
            document_text = raw.decode("utf-8")
            document = chunk_document(document_text)
            assert uncovered_characters(document_text, document) == 0, entry["file"]
            assert all(document_text[c.start : c.end] == c.text and len(c.text) <= MAX_CHARS for c in document.chunks)
            assert document.chunks and document.disease and document.url.startswith("https://")
            total += len(document.chunks)
    assert len(manifest.text_files) == 85 and total > 85


@pytest.fixture
def crafted(tmp_path, owner_db):
    """A small archive with its own name, registered the way `load` registers archive 13."""
    tag = uuid.uuid4().hex[:10]
    archive = f"texts-{tag}.zip"
    name = f"synthetic_condition_{tag}.txt"
    doc = DOC.replace("Synthetic Condition", f"Synthetic Condition {tag}").replace("alphaword", f"alphaword{tag}")
    # The reference entry carries this run's own word too, so a search for it finds this run's chunk only.
    doc = doc.replace("A reference entry.", f"A reference entry refword{tag}.")
    words = len(doc[chunk_document(doc).body_start :].split())
    path = tmp_path / archive
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, doc.encode("utf-8"))
        z.writestr(
            "diseases_main.csv",
            f"id,name,category,summary,word_count,url\nD1,Synthetic Condition {tag},Sample Category,s,{words},"
            "https://example.org/synthetic\n",
        )
    manifest = Manifest(
        {archive: sha256_file(path)},
        [],
        [{"archive": archive, "file": name, "sha256": hashlib.sha256(doc.encode()).hexdigest()}],
    )
    text_source, main_source = source_id(archive, "*.txt"), source_id(archive, "diseases_main.csv")
    with owner_db.transaction(None) as tx:
        from feeltriva_api.models import MappingRelease
        from feeltriva_ingestion.load import RELEASE_ID

        if tx.get(MappingRelease, RELEASE_ID) is None:
            tx.add(MappingRelease(release_id=RELEASE_ID, version="lexical-0"))
        tx.add(Source(source_id=text_source, source_name=f"{archive}/*.txt", version="t", sha256="0" * 64))
        tx.add(Source(source_id=main_source, source_name=f"{archive}/diseases_main.csv", version="t", sha256="0" * 64))
        tx.flush()
        tx.add(
            SourceRecord(
                record_id=f"rec_{tag}_text",
                source_id=text_source,
                file_path=name,
                row_number=None,
                content_hash="h",
                raw_object_uri=f"zip://{archive}#{name}",
            )
        )
        tx.add(
            SourceRecord(
                record_id=f"rec_{tag}_main",
                source_id=main_source,
                file_path="diseases_main.csv",
                row_number=1,
                content_hash="h",
                raw_object_uri=f"zip://{archive}#diseases_main.csv:row=1",
            )
        )
    return tmp_path, archive, manifest, tag, doc


@pytest.mark.postgres
def test_chunks_are_stored_pending_searchable_and_idempotent(crafted, owner_db):
    raw_dir, archive, manifest, tag, doc = crafted
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    totals = load_chunks(raw_dir, url, manifest, archive=archive)
    assert check(totals, 1) == []
    assert (
        totals["files"] == 1 and totals["uncovered_characters"] == 0 and totals["chunks_inserted"] == totals["chunks"]
    )
    assert totals["stored"]["release_status"] == "pending" and totals["category_flags_added"] == 1

    with owner_db.transaction(None) as tx:
        rows = tx.execute(
            text(
                """SELECT c.chunk_text, c.metadata, c.search_vector IS NOT NULL, r.status
               FROM evidence_chunks c JOIN knowledge_releases r ON r.release_id = c.knowledge_release_id
               WHERE c.record_id = :r ORDER BY (c.metadata ->> 'char_start')::int"""
            ),
            {"r": f"rec_{tag}_text"},
        ).all()
        flags = tx.execute(
            text("SELECT quality_flags FROM source_records WHERE record_id = :r"), {"r": f"rec_{tag}_main"}
        ).scalar_one()
    assert len(rows) == totals["chunks"] and flags == ["source_category_unreviewed"]
    for chunk_text, metadata, has_vector, status in rows:
        assert doc[metadata["char_start"] : metadata["char_end"]] == chunk_text  # the stored offsets re-read the source
        assert has_vector and status == "pending"  # searchable, never served
        assert metadata["source_category_unreviewed"] == "Sample Category"  # kept, explicitly untrusted
        assert metadata["disease_label"] == f"Synthetic Condition {tag}" and metadata["disease_id"].startswith("dis_")
        assert (
            metadata["source_url"] == "https://example.org/synthetic" and metadata["extraction_version"] == "sections-1"
        )
        assert metadata["word_count_declared"] == metadata["word_count_measured"]
    assert [m["chunk_index"] for _, m, _, _ in rows] == list(range(len(rows)))

    hits = search_chunks(url, f"alphaword{tag}")
    assert len(hits) == 1 and hits[0]["release_status"] == "pending" and hits[0]["section_path"] == []
    # Boilerplate is hidden by default. The search is for this run's own word: the test database keeps the rows
    # of earlier runs, and a search for words every run uses returned more than its limit (BUG-026).
    assert search_chunks(url, f"refword{tag}") == []
    with_refs = search_chunks(url, f"refword{tag}", include_boilerplate=True)
    assert [h["disease"] for h in with_refs] == [f"Synthetic Condition {tag}"]

    again = load_chunks(raw_dir, url, manifest, archive=archive)
    assert again["chunks_inserted"] == 0 and again["category_flags_added"] == 0 and check(again, 1) == []
    with owner_db.transaction(None) as tx:
        approved = tx.execute(
            text("SELECT count(*) FROM knowledge_releases WHERE release_id = :k AND status <> 'pending'"),
            {"k": KNOWLEDGE_RELEASE_ID},
        ).scalar_one()
    assert approved == 0


@pytest.mark.postgres
def test_tampered_file_and_missing_records_are_refused(crafted, owner_db):
    raw_dir, archive, manifest, _tag, _doc = crafted
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    wrong = Manifest(manifest.archives, [], [{**manifest.text_files[0], "sha256": "0" * 64}])
    totals = load_chunks(raw_dir, url, wrong, archive=archive)
    assert totals["chunks"] == 0 and totals["digest_mismatches"] == [manifest.text_files[0]["file"]]
    assert any("digest_mismatches" in d for d in check(totals, 1))
    extra = Manifest(manifest.archives, [], [*manifest.text_files, {**manifest.text_files[0], "file": "other.txt"}])
    with pytest.raises(SystemExit, match="run `load` first"):
        load_chunks(raw_dir, url, extra, archive=archive)
