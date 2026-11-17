"""Cell-level feature values on a small crafted matrix (PostgreSQL only; no source data needed)."""

from __future__ import annotations

import os
import uuid
import zipfile

import pytest
from feeltriva_api.models import Feature, FeatureMapping, MappingRelease, Source
from feeltriva_ingestion.archives import Manifest, sha256_file
from feeltriva_ingestion.cases import load_cases
from feeltriva_ingestion.features import check, load_case_features
from feeltriva_ingestion.load import source_id
from sqlalchemy import text

pytestmark = pytest.mark.postgres

HEADER = ["disease", "f1", "f2", "dup", "dup", "f3"]
ROWS = [
    "Flu,1,0,1,1,0",  # row 1: f1 affirmed; both 'dup' positions agree on 1
    "Flu,0,0,1,0,0",  # row 2: the two 'dup' positions disagree
    "Cold,0,0,0,0,0",  # row 3: nothing affirmed
    "Cold,1,,2,2,1",  # row 4: blank f2; non-binary value in both 'dup' positions (they agree)
    "short,row",  # row 5: malformed
]
FILE = "matrix.csv"


@pytest.fixture
def crafted(tmp_path, owner_db):
    tag = uuid.uuid4().hex[:10]
    archive = f"matrix-{tag}.zip"
    path = tmp_path / archive
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(FILE, ",".join(HEADER) + "\n" + "\n".join(ROWS) + "\n")
    manifest = Manifest(
        {archive: sha256_file(path)},
        [
            {
                "archive": archive,
                "file": FILE,
                "expected_rows": 5,
                "exact_unique_rows": 5,
                "adapter": "positional_feature_matrix",
                "targets": ["source_records", "dataset_cases", "case_labels"],
            }
        ],
        [],
    )
    sid = source_id(archive, FILE)
    with owner_db.transaction(None) as tx:
        tx.add(Source(source_id=sid, source_name=f"{archive}/{FILE}", version="t", sha256="0" * 64))
        tx.add(MappingRelease(release_id=f"rel-{tag}", version=f"v-{tag}"))
        tx.flush()
        for index in range(1, 6):
            term = HEADER[index]
            feature_id = f"feat_{tag}_{term}"
            if tx.get(Feature, feature_id) is None:
                tx.add(Feature(feature_id=feature_id, preferred_name=term, kind="other", value_type="boolean"))
                tx.flush()
            tx.add(
                FeatureMapping(
                    mapping_id=f"fm_{tag}_{index}",
                    release_id=f"rel-{tag}",
                    source_id=sid,
                    file_path=FILE,
                    column_index=index,
                    original_term=term,
                    feature_id=feature_id,
                )
            )
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    load_cases(tmp_path, url, manifest)
    return tmp_path, archive, manifest, tag, url


def _cells(owner_db, sid):
    """{(row_number, column_index): (raw_value, normalized_value, presence, conflict)}"""
    with owner_db.transaction(None) as tx:
        rows = tx.execute(
            text(
                """SELECT r.row_number, fm.column_index, cf.raw_value, cf.normalized_value, cf.presence, cf.conflict
               FROM case_features cf JOIN feature_mappings fm USING (mapping_id)
               JOIN dataset_cases c USING (case_id) JOIN source_records r USING (record_id)
               WHERE fm.source_id = :s"""
            ),
            {"s": sid},
        )
        return {(r[0], r[1]): tuple(r[2:]) for r in rows}


def test_values_are_stored_without_inventing_absence(crafted, owner_db):
    raw_dir, archive, manifest, _tag, url = crafted
    result = load_case_features(raw_dir, url, manifest, batch_rows=3)  # small batches: batch boundaries
    key = f"{archive}/{FILE}"
    cells = _cells(owner_db, source_id(archive, FILE))

    # Row 1: affirmed cells are 'present'; a repeated header keeps one row per position.
    assert cells[(1, 1)] == ("1", True, "present", False)
    assert cells[(1, 3)] == cells[(1, 4)] == ("1", True, "present", False)
    # A zero is never stored as a row, so it can never be read as an explicit denial.
    assert (1, 2) not in cells and (1, 5) not in cells
    assert not any(row == 3 for row, _ in cells)  # row 3 is all zeros: no rows at all

    # Row 2: the positions of 'dup' disagree. Both sides are kept, flagged, and neither wins.
    assert cells[(2, 3)] == ("1", True, "uncertain", True)
    assert cells[(2, 4)] == ("0", False, "uncertain", True)
    assert (2, 1) not in cells

    # Row 4: a blank is 'not asked', not a zero; an unexpected value is kept verbatim and uncertain.
    assert cells[(4, 2)] == ("", None, "not_asked", False)
    assert cells[(4, 3)] == cells[(4, 4)] == ("2", None, "uncertain", False)
    assert cells[(4, 1)] == cells[(4, 5)] == ("1", True, "present", False)

    assert len(cells) == 10 and not any(row == 5 for row, _ in cells)  # malformed row contributes nothing
    assert not any(v[2] == "absent" for v in cells.values())

    counts, stored = result["files"][key], result["summary"][key]
    assert counts == {
        "rows_read": 5,
        "feature_columns": 5,
        "non_zero_cells": 9,
        "blank_cells": 1,
        "other_value_cells": 2,
        "conflict_groups": 1,
        "rows_inserted": 10,
        "malformed_rows": 1,
    }
    assert (stored["rows"], stored["non_zero_rows"], stored["zero_rows"], stored["conflict_rows"]) == (10, 9, 1, 2)
    assert stored["zero_rows_outside_conflicts"] == 0 and stored["absent_rows"] == 0
    assert stored["conflict_cases_by_header"] == {"dup": 1}
    audit = [{"archive": archive, "file": FILE, "duplicate_column_disagreement_rows": {"dup": 1}}]
    assert check(result, audit) == []
    audit[0]["duplicate_column_disagreement_rows"] = {"dup": 2}
    assert check(result, audit) == [f"{key}: repeated-header conflicts differ from data_audit/audit.json"]


def test_rerun_inserts_nothing(crafted, owner_db):
    raw_dir, archive, manifest, _tag, url = crafted
    load_case_features(raw_dir, url, manifest)
    before = _cells(owner_db, source_id(archive, FILE))
    again = load_case_features(raw_dir, url, manifest)
    assert again["files"][f"{archive}/{FILE}"]["rows_inserted"] == 0
    assert _cells(owner_db, source_id(archive, FILE)) == before


def test_schema_drift_stops_the_load(crafted, owner_db):
    raw_dir, archive, manifest, tag, url = crafted
    with owner_db.transaction(None) as tx:  # the registered mapping now disagrees with the file's header
        tx.execute(
            text("UPDATE feature_mappings SET original_term = 'renamed' WHERE mapping_id = :m"), {"m": f"fm_{tag}_2"}
        )
    with pytest.raises(SystemExit, match="schema drift"):
        load_case_features(raw_dir, url, manifest)
    assert _cells(owner_db, source_id(archive, FILE)) == {}  # nothing was loaded


def test_cases_and_mappings_must_exist_first(tmp_path, owner_db):
    archive = f"bare-{uuid.uuid4().hex[:8]}.zip"
    with zipfile.ZipFile(tmp_path / archive, "w") as z:
        z.writestr(FILE, "disease,f1\nFlu,1\n")
    manifest = Manifest(
        {archive: sha256_file(tmp_path / archive)},
        [
            {
                "archive": archive,
                "file": FILE,
                "expected_rows": 1,
                "exact_unique_rows": 1,
                "adapter": "positional_feature_matrix",
                "targets": ["dataset_cases"],
            }
        ],
        [],
    )
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    with pytest.raises(SystemExit, match="no column mappings"):
        load_case_features(tmp_path, url, manifest)
    sid = source_id(archive, FILE)
    tag = uuid.uuid4().hex[:8]
    with owner_db.transaction(None) as tx:
        tx.add(Source(source_id=sid, source_name=f"{archive}/{FILE}", version="t", sha256="0" * 64))
        tx.add(MappingRelease(release_id=f"rel-{tag}", version=f"v-{tag}"))
        tx.add(Feature(feature_id=f"feat_{tag}", preferred_name="f1", kind="other", value_type="boolean"))
        tx.flush()
        tx.add(
            FeatureMapping(
                mapping_id=f"fm_{tag}",
                release_id=f"rel-{tag}",
                source_id=sid,
                file_path=FILE,
                column_index=1,
                original_term="f1",
                feature_id=f"feat_{tag}",
            )
        )
    with pytest.raises(SystemExit, match="run `load-cases` first"):
        load_case_features(tmp_path, url, manifest)
