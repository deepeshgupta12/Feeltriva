"""Symptom lists and declared-count checks on crafted archives (PostgreSQL only)."""

from __future__ import annotations

import os
import uuid
import zipfile

import pytest
from feeltriva_api.models import Feature, FeatureMapping, MappingRelease, Source
from feeltriva_ingestion.archives import Manifest, sha256_file
from feeltriva_ingestion.cases import load_cases
from feeltriva_ingestion.lists import (
    COUNT_FLAG,
    EMPTY_FLAG,
    check,
    feature_candidate_id,
    list_mapping_id,
    load_symptom_lists,
    parse_list,
)
from feeltriva_ingestion.load import RELEASE_ID, source_id
from sqlalchemy import text

pytestmark = pytest.mark.postgres

LIST_FILE, MATRIX_FILE = "lists.csv", "matrix.csv"
TARGETS = ["source_records", "dataset_cases", "case_labels"]


def test_parse_list_is_plain_comma_splitting():
    assert parse_list("fever, Back  Pain ,cough") == ["fever", "Back  Pain", "cough"]
    assert parse_list("") == [] and parse_list(" , ,") == []
    assert parse_list("anxiety and nervousness") == ["anxiety and nervousness"]  # 'and' is part of a term


@pytest.fixture
def crafted(tmp_path, owner_db):
    tag = uuid.uuid4().hex[:10]
    # Terms are unique per run so the persistent test database never supplies them by accident.
    known, fresh = f"back pain {tag}", f"new symptom {tag}"
    rows = [
        f'1,30,Male,"fever {tag}, Back  Pain {tag} , cough {tag}",3,Flu',  # spacing/case differ from the candidate
        f'2,41,Female,"fever {tag}, fever {tag}",2,Flu',  # the same term twice in one list
        f'3,50,Other,"cough {tag}",4,Cold',  # declared 4, listed 1
        '4,22,Male,"",0,Cold',  # empty list
        f'5,33,Female,"{fresh}, cough {tag}",2,Cold',  # a term no column has
        "short,row",  # malformed
    ]
    archive = f"lists-{tag}.zip"
    path = tmp_path / archive
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(LIST_FILE, "Patient_ID,Age,Gender,Symptoms,Symptom_Count,Disease\n" + "\n".join(rows) + "\n")
        z.writestr(
            MATRIX_FILE,
            "PATIENT_ID,AGE,SEX,DISEASE,E_1,E_2,SYMPTOM_COUNT\n"
            "1,30,M,Flu,1,1,2\n"  # declared 2, affirmed 2
            "2,31,F,Flu,1,0,2\n"  # declared 2, affirmed 1
            "3,32,F,Cold,0,0,0\n",
        )
    manifest = Manifest(
        {archive: sha256_file(path)},
        [
            {
                "archive": archive,
                "file": LIST_FILE,
                "expected_rows": 6,
                "exact_unique_rows": 6,
                "adapter": "symptom_list",
                "targets": TARGETS,
            },
            {
                "archive": archive,
                "file": MATRIX_FILE,
                "expected_rows": 3,
                "exact_unique_rows": 3,
                "adapter": "positional_feature_matrix",
                "targets": TARGETS,
            },
        ],
        [],
    )
    list_sid, matrix_sid = source_id(archive, LIST_FILE), source_id(archive, MATRIX_FILE)
    with owner_db.transaction(None) as tx:
        if tx.get(MappingRelease, RELEASE_ID) is None:
            tx.add(MappingRelease(release_id=RELEASE_ID, version="lexical-0"))
        tx.add(Source(source_id=list_sid, source_name=f"{archive}/{LIST_FILE}", version="t", sha256="0" * 64))
        tx.add(Source(source_id=matrix_sid, source_name=f"{archive}/{MATRIX_FILE}", version="t", sha256="0" * 64))
        # A candidate that already exists, as if a matrix column had produced it.
        tx.add(
            Feature(
                feature_id=feature_candidate_id(known),
                preferred_name="from the matrix crosswalk",
                kind="other",
                value_type="boolean",
            )
        )
        tx.flush()
        for index, term in ((4, "E_1"), (5, "E_2")):
            tx.add(Feature(feature_id=f"feat_{tag}_{term}", preferred_name=term, kind="other", value_type="boolean"))
            tx.flush()
            tx.add(
                FeatureMapping(
                    mapping_id=f"fm_{tag}_{index}",
                    release_id=RELEASE_ID,
                    source_id=matrix_sid,
                    file_path=MATRIX_FILE,
                    column_index=index,
                    original_term=term,
                    feature_id=f"feat_{tag}_{term}",
                )
            )
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    load_cases(tmp_path, url, manifest)
    return tmp_path, archive, manifest, tag, url, known, fresh


def _stored(owner_db, sid):
    with owner_db.transaction(None) as tx:
        cells = [
            tuple(r)
            for r in tx.execute(
                text(
                    """SELECT r.row_number, fm.original_term, cf.raw_value, cf.presence, cf.conflict, fm.feature_id
               FROM case_features cf JOIN feature_mappings fm USING (mapping_id)
               JOIN dataset_cases c USING (case_id) JOIN source_records r USING (record_id)
               WHERE fm.source_id = :s ORDER BY r.row_number, cf.raw_value"""
                ),
                {"s": sid},
            )
        ]
        flags = dict(
            tx.execute(
                text("SELECT row_number, quality_flags FROM source_records WHERE source_id = :s"), {"s": sid}
            ).all()
        )
        mappings = [
            tuple(r)
            for r in tx.execute(
                text(
                    """SELECT original_term, column_index, feature_id, zero_semantics, status, transformation
               FROM feature_mappings WHERE source_id = :s ORDER BY original_term"""
                ),
                {"s": sid},
            )
        ]
    return cells, flags, mappings


def test_lists_become_pending_mappings_and_feature_rows(crafted, owner_db):
    raw_dir, archive, manifest, tag, url, known, fresh = crafted
    result = load_symptom_lists(raw_dir, url, manifest, batch_rows=3)
    key = f"{archive}/{LIST_FILE}"
    sid = source_id(archive, LIST_FILE)
    cells, flags, mappings = _stored(owner_db, sid)

    # One list mapping per distinct term: no column position, pending, 'not listed' is unknown.
    assert [m[0] for m in mappings] == [f"Back  Pain {tag}", f"cough {tag}", f"fever {tag}", fresh]
    for original, column_index, _feature, zero, status, transformation in mappings:
        assert (column_index, zero, status) == (None, "unknown", "pending"), original
        assert transformation["list_column_name"] == "Symptoms" and transformation["not_listed_means"] == "unknown"
    by_term = {m[0]: m for m in mappings}

    # Lexically equal to an existing candidate -> linked to it; nothing duplicated or overwritten.
    assert by_term[f"Back  Pain {tag}"][2] == feature_candidate_id(known)
    with owner_db.transaction(None) as tx:
        reused = tx.get(Feature, feature_candidate_id(known))
        created = tx.get(Feature, feature_candidate_id(fresh))
        assert reused.preferred_name == "from the matrix crosswalk"  # the existing record is untouched
        assert (created.preferred_name, created.status, created.kind) == (fresh, "pending", "other")

    # One row per listed term per case, wording as written, all 'present', nothing 'absent'.
    by_row: dict[int, list[str]] = {}
    for row_number, _term, raw, presence, conflict, _f in cells:
        assert (presence, conflict) == ("present", False)
        by_row.setdefault(row_number, []).append(raw)
    assert by_row == {
        1: [f"Back  Pain {tag}", f"cough {tag}", f"fever {tag}"],
        2: [f"fever {tag}"],
        3: [f"cough {tag}"],
        5: [f"cough {tag}", fresh],
    }
    assert 4 not in by_row and 6 not in by_row  # empty list and malformed row contribute nothing

    # Declared counts are a quality check only.
    assert flags[3] == [COUNT_FLAG] and flags[4] == [EMPTY_FLAG]
    assert flags[1] == [] and flags[2] == [] and flags[5] == []  # "fever, fever" still declares 2 items
    assert flags[6] == ["malformed_row"]

    counts = result["files"][key]
    assert (counts["rows_read"], counts["items"], counts["distinct_terms"]) == (6, 8, 4)
    assert (counts["duplicate_items_in_a_row"], counts["empty_lists"], counts["malformed_rows"]) == (1, 1, 1)
    assert (counts["new_feature_candidates"], counts["terms_reusing_existing_candidates"]) == (3, 1)
    assert (counts["rows_inserted"], counts["declared_count_mismatches"]) == (7, 1)
    assert result["summary"][key] == {
        "rows": 7,
        "terms_used": 4,
        "cases_with_items": 4,
        "present_rows": 7,
        "absent_rows": 0,
        "list_mappings": 4,
    }
    assert check(result) == []


def test_matrix_declared_count_is_checked_against_affirmed_columns(crafted, owner_db):
    raw_dir, archive, manifest, _tag, url, _known, _fresh = crafted
    result = load_symptom_lists(raw_dir, url, manifest)
    assert result["matrix_counts"] == {
        f"{archive}/{MATRIX_FILE}": {
            "rows_checked": 3,
            "feature_columns": 2,
            "declared_count_mismatches": 1,
            "count_flags_added": 1,
        }
    }
    _cells, flags, _mappings = _stored(owner_db, source_id(archive, MATRIX_FILE))
    assert flags == {1: [], 2: [COUNT_FLAG], 3: []}


def test_rerun_changes_nothing(crafted, owner_db):
    raw_dir, archive, manifest, _tag, url, _known, _fresh = crafted
    load_symptom_lists(raw_dir, url, manifest)
    before = (_stored(owner_db, source_id(archive, LIST_FILE)), _stored(owner_db, source_id(archive, MATRIX_FILE)))
    again = load_symptom_lists(raw_dir, url, manifest)
    counts = again["files"][f"{archive}/{LIST_FILE}"]
    assert (counts["rows_inserted"], counts["new_feature_candidates"]) == (0, 0)
    assert (counts["count_flags_added"], counts["empty_flags_added"]) == (0, 0)
    assert again["matrix_counts"][f"{archive}/{MATRIX_FILE}"]["count_flags_added"] == 0
    after = (_stored(owner_db, source_id(archive, LIST_FILE)), _stored(owner_db, source_id(archive, MATRIX_FILE)))
    assert before == after and check(again) == []


def test_list_and_column_terms_share_one_candidate_id():
    assert feature_candidate_id("Shortness  of Breath") == feature_candidate_id("shortness of breath")
    assert feature_candidate_id("cough") != feature_candidate_id("dry cough")  # no semantic merging
    assert list_mapping_id("src_a", "cough") != list_mapping_id("src_b", "cough")  # scoped to the source


def test_cases_must_be_loaded_first(tmp_path, owner_db):
    archive = f"bare-{uuid.uuid4().hex[:8]}.zip"
    with zipfile.ZipFile(tmp_path / archive, "w") as z:
        z.writestr(LIST_FILE, 'Patient_ID,Symptoms,Disease\n1,"fever",Flu\n')
    manifest = Manifest(
        {archive: sha256_file(tmp_path / archive)},
        [
            {
                "archive": archive,
                "file": LIST_FILE,
                "expected_rows": 1,
                "exact_unique_rows": 1,
                "adapter": "symptom_list",
                "targets": TARGETS,
            }
        ],
        [],
    )
    with pytest.raises(SystemExit, match="run `load-cases` first"):
        load_symptom_lists(tmp_path, os.environ["TEST_MIGRATION_DATABASE_URL"], manifest)
