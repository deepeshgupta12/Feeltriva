"""Row-level case loading on a small crafted archive (PostgreSQL only; no source data needed)."""

from __future__ import annotations

import json
import os
import uuid
import zipfile

import pytest
from feeltriva_api.models import Source
from feeltriva_ingestion.archives import Manifest, sha256_file
from feeltriva_ingestion.cases import SPLIT_FLAG, compare_with_manifest, load_cases, original_split
from feeltriva_ingestion.load import disease_candidate_id, source_id
from sqlalchemy import text

pytestmark = pytest.mark.postgres

HEADER = "PATIENT_ID,AGE,SEX,DISEASE,f1,f2\n"
TRAIN = HEADER + (
    "1,30,F,Flu,1,0\n"  # row 1
    "2,41,M,Flu,1,0\n"  # row 2: different demographics -> different profile
    "3,30,F,Cold,1,0\n"  # row 3: same profile as row 1, different label -> ambiguity kept
    "1,30,F,Flu,1,0\n"  # row 4: exact duplicate of row 1
    "5,abc,F,Flu,0,1\n"  # row 5: age cannot be parsed
    "short,row\n"  # row 6: malformed
)
TEST = HEADER + (
    "9,30,F,Flu,1,0\n"  # row 1: same profile as train rows 1, 3, 4 -> shared across the split
    "10,77,M,Other,0,0\n"  # row 2
)


@pytest.fixture
def crafted(tmp_path, owner_db):
    """A two-file 'train/test' archive registered as two sources, unique per test run."""
    archive = f"crafted-{uuid.uuid4().hex[:10]}.zip"
    path = tmp_path / archive
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("train.csv", TRAIN)
        z.writestr("test.csv", TEST)
    targets = ["source_records", "dataset_cases", "case_labels"]
    manifest = Manifest(
        {archive: sha256_file(path)},
        [
            {"archive": archive, "file": "train.csv", "expected_rows": 6, "exact_unique_rows": 5, "targets": targets},
            {"archive": archive, "file": "test.csv", "expected_rows": 2, "exact_unique_rows": 2, "targets": targets},
        ],
        [],
    )
    with owner_db.transaction(None) as tx:
        for file in ("train.csv", "test.csv"):
            tx.add(
                Source(
                    source_id=source_id(archive, file), source_name=f"{archive}/{file}", version="t", sha256="0" * 64
                )
            )
    return tmp_path, archive, manifest


def _rows(owner_db, archive, file):
    with owner_db.transaction(None) as tx:
        return {
            r.row_number: r
            for r in tx.execute(
                text(
                    """SELECT r.row_number, r.content_hash, r.original_split, r.quality_flags, r.raw_object_uri,
                      c.case_id, c.source_patient_id, c.source_split, c.age_value, c.age_unit,
                      c.original_demographic_field, c.original_demographic_value, c.profile_cluster_id,
                      c.duplicate_status, l.original_label, l.disease_id, l.label_origin
               FROM source_records r LEFT JOIN dataset_cases c USING (record_id)
               LEFT JOIN case_labels l USING (case_id) WHERE r.source_id = :s"""
                ),
                {"s": source_id(archive, file)},
            )
        }


def test_cases_are_loaded_flagged_and_never_merged(crafted, owner_db):
    raw_dir, archive, manifest = crafted
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    result = load_cases(raw_dir, url, manifest, batch_rows=2)  # tiny batches: exercises batch boundaries
    assert compare_with_manifest(result, manifest) == []
    train_key, test_key = f"{archive}/train.csv", f"{archive}/test.csv"
    assert result["files"][train_key] == {
        "rows_read": 6,
        "records_inserted": 6,
        "cases_inserted": 5,
        "labels_inserted": 5,
        "batches": 3,
    }
    assert result["files"][test_key]["cases_inserted"] == 2

    train, test = _rows(owner_db, archive, "train.csv"), _rows(owner_db, archive, "test.csv")
    assert len(train) == 6 and len(test) == 2  # every source row is kept, including duplicates

    # Split names are namespaced by archive and recorded on both the record and the case.
    assert {r.original_split for r in train.values()} == {f"{archive}:train"}
    assert {r.source_split for r in test.values()} == {f"{archive}:test"}

    # Malformed row: kept as a flagged record, never becomes a case.
    assert train[6].quality_flags == ["malformed_row"] and train[6].case_id is None

    # Demographics are preserved as supplied; the age unit is not assumed; bad ages are flagged, not guessed.
    assert (train[1].original_demographic_field, train[1].original_demographic_value) == ("SEX", "F")
    assert float(train[1].age_value) == 30 and train[1].age_unit is None
    assert train[5].age_value is None and "age_not_parsed" in train[5].quality_flags
    assert train[1].source_patient_id == "1" and train[1].raw_object_uri.endswith("#train.csv:row=1")

    # Exact duplicates share a content hash; both rows remain and are marked.
    assert train[1].content_hash == train[4].content_hash != train[2].content_hash
    assert train[1].duplicate_status == train[4].duplicate_status == "exact_duplicate_row"

    # Same feature profile with a different label: one cluster, both labels kept (no vote, no merge).
    cluster = train[1].profile_cluster_id
    assert train[3].profile_cluster_id == train[4].profile_cluster_id == test[1].profile_cluster_id == cluster
    assert train[2].profile_cluster_id != cluster  # different demographics
    assert train[3].duplicate_status == "repeated_profile"
    assert (train[1].original_label, train[3].original_label) == ("Flu", "Cold")
    assert train[3].disease_id == disease_candidate_id("Cold") != train[1].disease_id
    assert {r.label_origin for r in train.values() if r.case_id} == {"unknown"}  # origin of labels is not known

    # The profile occurs in both original splits: every member is flagged as a leakage warning.
    flagged = {
        (name, n)
        for name, rows in (("train", train), ("test", test))
        for n, r in rows.items()
        if SPLIT_FLAG in r.quality_flags
    }
    assert flagged == {("train", 1), ("train", 3), ("train", 4), ("test", 1)}
    assert test[2].duplicate_status == "no_duplicate_detected" and test[2].quality_flags == []
    assert result["summary"][train_key]["rows_flagged_shared_across_split"] == 3
    assert result["summary"][train_key]["exact_unique_rows"] == 5

    # A source patient ID is scoped to its file: equal IDs in different files are different cases.
    assert train[1].case_id != test[1].case_id

    # Labels unknown to the crosswalk become pending lexical candidates, never approved ones.
    with owner_db.transaction(None) as tx:
        statuses = {
            r[0]
            for r in tx.execute(
                text("SELECT status FROM diseases WHERE disease_id = ANY(:ids)"),
                {"ids": [disease_candidate_id(x) for x in ("Flu", "Cold", "Other")]},
            )
        }
    assert statuses == {"pending"}


def test_rerun_is_idempotent(crafted, owner_db):
    raw_dir, archive, manifest = crafted
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    first = load_cases(raw_dir, url, manifest)
    before = json.dumps(
        {f: {n: tuple(r) for n, r in _rows(owner_db, archive, f).items()} for f in ("train.csv", "test.csv")},
        default=str,
        sort_keys=True,
    )
    second = load_cases(raw_dir, url, manifest)
    for counts in second["files"].values():
        assert (counts["records_inserted"], counts["cases_inserted"], counts["labels_inserted"]) == (0, 0, 0)
    assert second["finalise"] == {"duplicate_status_updates": 0, "split_overlap_flags_added": 0}
    assert second["summary"] == first["summary"]
    after = json.dumps(
        {f: {n: tuple(r) for n, r in _rows(owner_db, archive, f).items()} for f in ("train.csv", "test.csv")},
        default=str,
        sort_keys=True,
    )
    assert before == after


def test_unregistered_source_is_refused_and_split_detection_is_conservative(tmp_path):
    archive = f"lonely-{uuid.uuid4().hex[:8]}.zip"
    with zipfile.ZipFile(tmp_path / archive, "w") as z:
        z.writestr("train.csv", HEADER + "1,30,F,Flu,1,0\n")
    manifest = Manifest(
        {archive: sha256_file(tmp_path / archive)},
        [
            {
                "archive": archive,
                "file": "train.csv",
                "expected_rows": 1,
                "exact_unique_rows": 1,
                "targets": ["dataset_cases"],
            }
        ],
        [],
    )
    assert original_split(archive, "train.csv", manifest) is None  # a single file is not a split
    with pytest.raises(SystemExit, match="not registered"):
        load_cases(tmp_path, os.environ["TEST_MIGRATION_DATABASE_URL"], manifest)
