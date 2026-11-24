"""Ingestion completeness check (M1.13).

A check that cannot fail is worthless, so most of this file loads small crafted archives with the
real loaders, confirms the check passes, then damages the stored data in a transaction that is
rolled back and expects the check to report exactly that damage.

The full command against the six real archives is not a unit test (it takes minutes and needs the
loaded development database); its output is recorded in docs/ENGINEERING_LOG.md.
"""

from __future__ import annotations

import hashlib
import os
import uuid
import zipfile
from contextlib import contextmanager

import pytest
from feeltriva_api.models import (
    Disease,
    DiseaseMapping,
    Feature,
    FeatureMapping,
    MappingRelease,
    Source,
    SourceRecord,
    Statement,
    StatementSource,
)
from feeltriva_ingestion import completeness_cases
from feeltriva_ingestion.archives import Manifest, sha256_file
from feeltriva_ingestion.audit import audit_csv, norm_label
from feeltriva_ingestion.cases import load_cases
from feeltriva_ingestion.chunks import KNOWLEDGE_RELEASE_ID, load_chunks
from feeltriva_ingestion.completeness import (
    DOC,
    MISMATCH,
    SOURCE_FIELDS,
    Report,
    _evidence,
    _feature_rows,
    _reference,
    inspect_file,
    mapping_table,
    narrative_expectations,
    render,
    rows_recognised,
)
from feeltriva_ingestion.completeness_cases import ROLE_ROWS, TEXT_ROW, case_file_rows, split_rows
from feeltriva_ingestion.completeness_rows import _acceptance, _Named, _statement_file, _texts
from feeltriva_ingestion.evidence import load_evidence, whole_file_record_id
from feeltriva_ingestion.features import load_case_features
from feeltriva_ingestion.lists import load_symptom_lists
from feeltriva_ingestion.load import RELEASE_ID, _h, disease_candidate_id, source_id
from feeltriva_ingestion.verify_files import verify_statement_file, verify_text_files
from sqlalchemy import create_engine

TARGETS = ["source_records", "dataset_cases", "case_labels"]
A15 = "archive(15).zip"


# -- the handoff table and the report -----------------------------------------------------------


def test_the_check_walks_the_rows_of_the_handoff_mapping_table():
    table = mapping_table()
    assert len(table) == 27 and [row[0] for row in table] == list(SOURCE_FIELDS)
    assert rows_recognised(table) == 27
    assert table[4] == (
        "12 data.csv other 377 columns",
        "feature_mappings; case_features",
        "Positional binary attributes; zero semantics unresolved",
    )
    # Every row of the table is bound to a part of a file, to the text files, or to all files.
    bound = {row for roles in ROLE_ROWS.values() for row in roles.values()} | {1, TEXT_ROW}
    assert bound == set(range(1, 28))


def test_a_changed_handoff_table_is_reported_not_silently_checked(tmp_path):
    text = DOC.read_text(encoding="utf-8")
    renamed = tmp_path / "renamed.md"
    renamed.write_text(text.replace("| 14 `Age` |", "| 14 `Age in years` |"), encoding="utf-8")
    assert rows_recognised(mapping_table(renamed)) == 26
    shorter = tmp_path / "shorter.md"
    shorter.write_text("\n".join(line for line in text.splitlines() if "14 `Gender`" not in line), encoding="utf-8")
    assert rows_recognised(mapping_table(shorter)) == "26 rows in the document"


def test_report_marks_mismatches_later_work_and_rows_without_a_check():
    report = Report([("a", "x", ""), ("b", "y", ""), ("c", "z", "")])
    report.check(1, "rows", 5, 5, "manifest")
    report.check(2, "rows", 5, 4, "manifest")
    report.later(2, "classified", "0 of 5", "M2.7")
    assert [c.status for c in report.checks] == ["ok", MISMATCH, "later"]
    report.close()  # row 3 has no check at all: that is itself a mismatch
    assert [(c.row, c.measure) for c in report.mismatches] == [(2, "rows"), (3, "a check exists for this row")]
    assert [c.row for c in report.deferred] == [2]  # later work is listed, never counted as passed
    text = render(report)
    assert "[T2] b  ->  y" in text and "MISMATCH rows: expected 5, loaded 4  [manifest]" in text
    assert "later    classified: expected done in M2.7, loaded 0 of 5" in text


# -- helpers --------------------------------------------------------------------------------------


@contextmanager
def scratch(url):
    """A cursor in a transaction that is always rolled back."""
    engine = create_engine(url)
    connection = engine.raw_connection()
    try:
        yield connection.cursor()
    finally:
        connection.rollback()
        connection.close()
        engine.dispose()


def _mismatches(report):
    return [check.measure for check in report.mismatches]


STATED = "feature positions named in the mapping table"
# A reviewer's decision as the review path records it; the last argument is how many hours ago.
NOTE = (
    "INSERT INTO review_notes (note_id, target_type, target_id, reviewer, note, status_change, created_at) "
    "VALUES (gen_random_uuid(), %s, %s, 'dev-reviewer:test', 'Decided in a test.', %s, now() - %s * interval '1 hour')"
)


# -- case files: a crafted train/test matrix ----------------------------------------------------

HEADER = "PATIENT_ID,AGE,SEX,DISEASE,f1,dup,dup,SYMPTOM_COUNT\n"
TRAIN = HEADER + (
    "1,30,F,Flu,1,1,1,3\n"  # row 1
    "2,41,M,Flu,0,1,0,1\n"  # row 2: the two 'dup' positions disagree
    "3,30,F,Cold,1,1,1,3\n"  # row 3: same profile as row 1, different label
    "1,30,F,Flu,1,1,1,3\n"  # row 4: exact duplicate of row 1
    "5,abc,F,Flu,0,0,0,9\n"  # row 5: age is not a number; declared count 9, affirmed 0
    "short,row\n"  # row 6: malformed
)
TEST = HEADER + (
    "9,30,F,Flu,1,1,1,3\n"  # row 1: profile shared with train rows 1, 3, 4
    "10,77,M,Other,,0,0,0\n"  # row 2: blank cell
    "11,50,M,Other,7,0,0,0\n"  # row 3: a value that is neither 0 nor 1
)


@pytest.fixture
def matrix(tmp_path, owner_db, monkeypatch):
    tag = uuid.uuid4().hex[:10]
    archive, release = f"complete-{tag}.zip", f"rel-{tag}"
    path = tmp_path / archive
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("train.csv", TRAIN)
        z.writestr("test.csv", TEST)
    entry = {"adapter": "positional_feature_matrix", "targets": TARGETS, "expected_columns": 8}
    manifest = Manifest(
        {archive: sha256_file(path)},
        [
            {"archive": archive, "file": "train.csv", "expected_rows": 6, "exact_unique_rows": 5, **entry},
            {"archive": archive, "file": "test.csv", "expected_rows": 3, "exact_unique_rows": 3, **entry},
        ],
        [],
    )
    features = {4: f"feat_{tag}_f1", 5: f"feat_{tag}_dup", 6: f"feat_{tag}_dup"}
    headings = {4: "f1", 5: "dup", 6: "dup"}
    with owner_db.transaction(None) as tx:
        tx.add(MappingRelease(release_id=release, version=f"v-{tag}"))
        for feature_id in sorted(set(features.values())):
            tx.add(Feature(feature_id=feature_id, preferred_name=feature_id, kind="other", value_type="boolean"))
        for file in ("train.csv", "test.csv"):
            tx.add(Source(source_id=source_id(archive, file), source_name=f"{archive}/{file}", version="t", sha256="0"))
        tx.flush()
        for file in ("train.csv", "test.csv"):
            for index, feature_id in features.items():
                tx.add(
                    FeatureMapping(
                        mapping_id=f"fm_{tag}_{file[:2]}_{index}",
                        release_id=release,
                        source_id=source_id(archive, file),
                        file_path=file,
                        column_index=index,
                        original_term=headings[index],
                        feature_id=feature_id,
                    )
                )
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    load_cases(tmp_path, url, manifest)
    load_case_features(tmp_path, url, manifest)
    load_symptom_lists(tmp_path, url, manifest)  # no list file here: this runs the declared-count check
    load_evidence(url, manifest, narrative_sources=[])
    # The crafted files play the part of archive 15 (ID, age, sex, label, split, features, declared count).
    monkeypatch.setitem(
        ROLE_ROWS, (archive, "positional_feature_matrix"), ROLE_ROWS[(A15, "positional_feature_matrix")]
    )
    crosswalk = {index: (headings[index], features[index]) for index in features}
    return {
        "dir": tmp_path,
        "archive": archive,
        "manifest": manifest,
        "release": release,
        "url": url,
        "cross": crosswalk,
    }


def _world(cur, crafted):
    """What `gather` builds for the real archives, for the crafted case files only."""
    archive, manifest = crafted["archive"], crafted["manifest"]
    files = {
        (archive, entry["file"]): {"entry": entry, "sid": source_id(archive, entry["file"]), "kind": "case"}
        for entry in manifest.files
    }
    reference = _reference(cur, [info["sid"] for info in files.values()], crafted["release"])
    audit_files, audit_profiles, labels, profiles = {}, {}, {}, {}
    with zipfile.ZipFile(crafted["dir"] / archive) as z:
        for key, info in files.items():
            audit_files[key], found, audit_profiles[key] = audit_csv(z, archive, key[1])
            labels[key] = {label for label in ("Flu", "Cold", "Other") if norm_label(label) in found}
            inspect_file(cur, z, info, reference, manifest, profiles, {})
    return {
        "manifest": manifest,
        "audit": {
            "archive15_train_test_shared_profiles_excluding_patient_id": len(
                set.intersection(*audit_profiles.values())
            ),
            "union_lexical_disease_labels": len({disease_candidate_id(x) for found in labels.values() for x in found}),
            "overlap": [],
        },
        "audit_files": audit_files,
        "disease_cross": {key: {label: disease_candidate_id(label) for label in labels[key]} for key in files},
        "feature_cross": dict.fromkeys(files, crafted["cross"]),
        "files": files,
        "reference": reference,
        "feature_rows": _feature_rows(cur, reference),
        "evidence": _evidence(cur, files, "no-narrative-source"),
        "texts": {"files": 0, "records_with_file_digest": 0, "release_status": "pending"},
    }


def _case_report(cur, crafted):
    world = _world(cur, crafted)
    report = Report(mapping_table())
    for key, info in world["files"].items():
        case_file_rows(_Named(report, key[1]), world, key, info)
    split_rows(report, world)
    _acceptance(report, world)
    return report, world


def _register_label_mappings(owner_db, crafted):
    """The label crosswalk rows `load` would have written for the crafted files."""
    archive = crafted["archive"]
    with owner_db.transaction(None) as tx:
        for file, labels in (("train.csv", ("Flu", "Cold")), ("test.csv", ("Flu", "Other"))):
            for label in labels:
                if tx.get(Disease, disease_candidate_id(label)) is None:
                    tx.add(Disease(disease_id=disease_candidate_id(label), preferred_name=norm_label(label)))
                    tx.flush()
                tx.add(
                    DiseaseMapping(
                        mapping_id=f"dm_{uuid.uuid4().hex[:20]}",
                        release_id=crafted["release"],
                        source_id=source_id(archive, file),
                        original_label=label,
                        disease_id=disease_candidate_id(label),
                        method="lexical_casefold_whitespace",
                    )
                )


@pytest.mark.postgres
def test_correctly_loaded_case_files_pass_every_check(matrix, owner_db):
    _register_label_mappings(owner_db, matrix)
    with scratch(matrix["url"]) as cur:
        report, world = _case_report(cur, matrix)
    # The crafted files stand in for archive 15, whose row of the mapping table says "223 positions".
    # They have three, and the check holds them to the number the handoff states.
    assert _mismatches(report) == [f"{file}: {STATED}" for file in ("train.csv", "test.csv")]
    assert "feature positions named in the mapping table: expected 223, loaded 3  [docs/04]" in render(report)
    train = world["files"][(matrix["archive"], "train.csv")]["facts"]
    test = world["files"][(matrix["archive"], "test.csv")]["facts"]
    # The recount of the files, independent of the loaders.
    assert (train["rows"], train["malformed"], train["cases"], train["distinct_content"]) == (6, 1, 5, 5)
    assert train["rows_in_exact_duplicate_groups"] == 2 and train["age_not_parsed"] == 1
    assert train["declared_count_mismatches"] == 1 and train["conflict_cases"] == {"dup": 1}
    assert train["column_rows"][4:7] == [3, 4, 4]  # f1: three 1s; each 'dup' position: three 1s + one conflict row
    assert train["column_present"][4:7] == [3, 3, 3]  # the conflicting row is not counted as affirmed
    assert (train["conflict_rows"], train["conflict_zero_rows"]) == (2, 1)
    assert (test["blank_cells"], test["other_value_cells"]) == (1, 1)
    # Co-occurrence is counted per distinct case: the two 'dup' columns share one feature.
    flu = disease_candidate_id("Flu")
    assert train["label_cases"][flu] == 4 and train["cooccurrence"][flu][matrix["cross"][5][1]] == 2
    lines = render(report)
    assert "train.csv: cases whose source patient ID equals the file: expected 5, loaded 5" in lines
    assert "feature profiles (label included) present in more than one original split: expected 1, loaded 1" in lines
    assert (
        "rows flagged as sharing a feature profile across the original split (a leakage warning): expected 4" in lines
    )
    assert "feature positions classified as symptom, history, risk, measurement or other" in lines  # later work
    assert {check.row for check in report.deferred} == {21, 22}


def _row(sid, number):
    return "(SELECT record_id FROM source_records WHERE source_id = '" + sid + f"' AND row_number = {number})"


def _case(sid, number):
    return f"(SELECT case_id FROM dataset_cases WHERE record_id = {_row(sid, number)})"


@pytest.mark.postgres
def test_every_kind_of_damage_to_loaded_cases_is_reported(matrix, owner_db):
    _register_label_mappings(owner_db, matrix)
    archive = matrix["archive"]
    train, test = source_id(archive, "train.csv"), source_id(archive, "test.csv")
    tag = matrix["release"].removeprefix("rel-")
    f1, dup = f"fm_{tag}_tr_4", f"fm_{tag}_tr_5"
    damage = {
        "source patient ID equals the file": f"UPDATE dataset_cases SET source_patient_id = 'x' WHERE record_id = {_row(train, 1)}",
        "age value equals the file": f"UPDATE dataset_cases SET age_value = 31 WHERE record_id = {_row(train, 1)}",
        "age unit set": f"UPDATE dataset_cases SET age_unit = 'years' WHERE record_id = {_row(train, 1)}",
        "demographic field name and value are kept": (
            f"UPDATE dataset_cases SET original_demographic_value = 'Female' WHERE record_id = {_row(train, 1)}"
        ),
        "value counts": f"UPDATE dataset_cases SET original_demographic_value = 'Female' WHERE record_id = {_row(train, 1)}",
        "label and lexical candidate equal the file": (
            f"UPDATE case_labels SET original_label = 'Other' WHERE case_id = {_case(train, 1)}"
        ),
        "carrying their original split": f"UPDATE dataset_cases SET source_split = NULL WHERE record_id = {_row(train, 1)}",
        "differs from the file in any field": (
            f"UPDATE source_records SET content_hash = 'x' WHERE record_id = {_row(train, 1)}"
        ),
        "rows whose stored record or case differs": (  # a record is missing: rows no longer pair with the file
            f"UPDATE source_records SET row_number = 99 WHERE record_id = {_row(train, 2)}"
        ),
        "feature values stored": f"DELETE FROM case_features WHERE mapping_id = '{f1}' AND case_id = {_case(train, 1)}",
        "stored and affirmed counts both equal the file": (
            f"UPDATE case_features SET presence = 'uncertain' WHERE mapping_id = '{f1}' AND case_id = {_case(train, 1)}"
        ),
        "values marked absent": f"UPDATE case_features SET presence = 'absent' WHERE mapping_id = '{f1}'",
        "conflict rows stored": f"UPDATE case_features SET conflict = false WHERE mapping_id = '{dup}'",
        "repeated headings whose number of conflicting cases": (
            f"UPDATE case_features SET conflict = false WHERE mapping_id = '{dup}'"
        ),
        "mappings pending or decided by a reviewer": (
            f"UPDATE feature_mappings SET status = 'approved' WHERE mapping_id = '{f1}'"
        ),
        "none reading a zero as a denial": f"UPDATE feature_mappings SET zero_semantics = 'absent' WHERE mapping_id = '{f1}'",
        "only a reviewer may decide": f"UPDATE feature_mappings SET status = 'approved' WHERE mapping_id = '{f1}'",
        "headings found at their registered position": (
            f"UPDATE feature_mappings SET original_term = 'renamed' WHERE mapping_id = '{f1}'"
        ),
        "attached to a case of another source file": (
            "INSERT INTO case_features (case_id, mapping_id, raw_value, normalized_value, presence, conflict) "
            f"SELECT {_case(test, 2)}, '{f1}', '1', 'true'::jsonb, 'present'::presence_state, false"
        ),
        "declared count differs": f"UPDATE source_records SET quality_flags = '[]' WHERE record_id = {_row(train, 5)}",
        "ages that are not a number": f"UPDATE source_records SET quality_flags = '[]' WHERE record_id = {_row(train, 5)}",
        "sharing a feature profile across the original split": (
            f"UPDATE source_records SET quality_flags = '[]' WHERE record_id = {_row(test, 1)}"
        ),
        "do not share one cluster ID": (
            f"UPDATE dataset_cases SET profile_cluster_id = 'pc_other' WHERE record_id = {_row(train, 4)}"
        ),
        "marked as such on the case": (
            f"UPDATE dataset_cases SET duplicate_status = 'no_duplicate_detected' WHERE record_id = {_row(train, 4)}"
        ),
        "count, denominator or frequency differs": (
            "UPDATE disease_feature_evidence SET frequency = 0.123456 "
            f"WHERE record_id = '{whole_file_record_id(train)}'"
        ),
        "label-feature pairs with at least one affirming case": (
            f"DELETE FROM disease_feature_evidence WHERE record_id = '{whole_file_record_id(train)}'"
        ),
        "label spellings mapped exactly as in the crosswalk": (
            f"DELETE FROM disease_mappings WHERE source_id = '{train}' AND original_label = 'Cold'"
        ),
        "case labels with no mapping in the crosswalk": (
            f"DELETE FROM disease_mappings WHERE source_id = '{train}' AND original_label = 'Cold'"
        ),
        "whose origin is recorded as anything but unknown": (
            f"UPDATE case_labels SET label_origin = 'clinician' WHERE case_id = {_case(train, 1)}"
        ),
    }
    for expected, statement in damage.items():
        with scratch(matrix["url"]) as cur:
            cur.execute(statement)
            assert cur.rowcount > 0, f"the damage for {expected!r} changed nothing"
            report, _world_ = _case_report(cur, matrix)
        found = [measure for measure in _mismatches(report) if not measure.endswith(STATED)]
        assert any(expected in measure for measure in found), f"{expected!r} was not reported; reported: {found}"
    with scratch(matrix["url"]) as cur:  # every change above was rolled back
        assert all(measure.endswith(STATED) for measure in _mismatches(_case_report(cur, matrix)[0]))


@pytest.mark.postgres
def test_a_file_whose_columns_changed_is_reported_and_not_compared(matrix, owner_db):
    wider = Manifest(
        matrix["manifest"].archives,
        [{**entry, "expected_columns": 9} for entry in matrix["manifest"].files],
        [],
    )
    with scratch(matrix["url"]) as cur:
        report, world = _case_report(cur, {**matrix, "manifest": wider})
    assert all(info["facts"] is None for info in world["files"].values())
    found = _mismatches(report)
    assert found and all("layout" in measure for measure in found if measure.startswith(("train", "test")))
    assert "expected as registered, loaded differs (source schema drift)" in render(report)


# -- symptom lists --------------------------------------------------------------------------------


@pytest.mark.postgres
def test_symptom_list_rows_are_checked_per_term(tmp_path, owner_db, monkeypatch):
    tag = uuid.uuid4().hex[:10]
    archive, file = f"complete-list-{tag}.zip", "lists.csv"
    rows = [
        f'1,30,Male,"fever {tag}, Back  Pain {tag}, Fiebre Añeja {tag}",3,Flu',  # a term outside ASCII
        f'2,41,Female,"fever {tag}, fever {tag}",2,Flu',  # the same term twice: one stored item
        f'3,50,Other,"cough {tag}",4,Cold',  # declared 4, listed 1
        '4,22,Male,"",0,Cold',  # empty list
    ]
    path = tmp_path / archive
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(file, "Patient_ID,Age,Gender,Symptoms,Symptom_Count,Disease\n" + "\n".join(rows) + "\n")
    entry = {"archive": archive, "file": file, "expected_rows": 4, "exact_unique_rows": 4, "expected_columns": 6}
    manifest = Manifest({archive: sha256_file(path)}, [{**entry, "adapter": "symptom_list", "targets": TARGETS}], [])
    sid = source_id(archive, file)
    with owner_db.transaction(None) as tx:
        if tx.get(MappingRelease, RELEASE_ID) is None:
            tx.add(MappingRelease(release_id=RELEASE_ID, version="lexical-0"))
        tx.add(Source(source_id=sid, source_name=f"{archive}/{file}", version="t", sha256="0"))
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    load_cases(tmp_path, url, manifest)
    load_symptom_lists(tmp_path, url, manifest)
    monkeypatch.setitem(ROLE_ROWS, (archive, "symptom_list"), ROLE_ROWS[("archive(14).zip", "symptom_list")])
    crafted = {
        "dir": tmp_path,
        "archive": archive,
        "manifest": manifest,
        "release": RELEASE_ID,
        "url": url,
        "cross": {},
    }

    def run(cur):
        world = _world(cur, crafted)
        report = Report(mapping_table())
        key = (archive, file)
        case_file_rows(report, world, key, world["files"][key])
        return report, world["files"][key]["facts"]

    with scratch(url) as cur:
        report, facts = run(cur)
    listed = [m for m in _mismatches(report) if "label" not in m]  # label mappings are not registered here
    assert listed == []
    assert (facts["items"], facts["duplicate_items"], facts["empty_lists"]) == (6, 1, 1)
    # Terms are compared after case folding, also outside ASCII ("Añeja" and "añeja" are one term).
    assert facts["term_cases"] == {
        f"fever {tag}": 2,
        f"back pain {tag}": 1,
        f"fiebre añeja {tag}": 1,
        f"cough {tag}": 1,
    }
    assert facts["declared_count_mismatches"] == 1
    text = render(report)
    assert "listed items stored (one per distinct term per case): expected 5, loaded 5" in text
    assert "[T19] 14 `Symptom_Count`" in text and "flagged on the record: expected 1, loaded 1" in text

    with scratch(url) as cur:  # one listed item lost
        cur.execute(
            "DELETE FROM case_features WHERE case_id = " + _case(sid, 3) + " RETURNING mapping_id",
        )
        assert cur.fetchall()
        report, _facts = run(cur)
    found = _mismatches(report)
    assert any("listed items stored" in m for m in found) and any("terms whose stored count" in m for m in found)


# -- narrative tables -----------------------------------------------------------------------------


@pytest.mark.postgres
def test_narrative_rows_are_compared_with_their_statements(tmp_path, owner_db):
    tag = uuid.uuid4().hex[:10]
    archive, file = f"complete-narrative-{tag}.zip", "symptoms.csv"
    name = f"Synthetic Condition {tag}"
    main_rows = [
        {
            "id": "D1",
            "name": name,
            "category": "Sample",
            "summary": "s",
            "word_count": "3",
            "url": "https://example.org/d1",
        }
    ]
    lines = [
        ["D1", name, "Señal de ejemplo — naïve café ñandú 症状"],  # text outside ASCII is kept and compared exactly
        ["D1", name.upper(), "Sample sign beta"],  # the redundant name differs only by case: no flag
        ["D1", "Another name", "Sample sign gamma"],  # the redundant name disagrees: flagged
        ["D9", name, "Sample sign delta"],  # native ID not in the disease table: flagged
        ["D1", name, ""],  # no text: a record, but no statement
    ]
    path = tmp_path / archive
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(file, "disease_id,disease_name,symptom\n" + "\n".join(",".join(cells) for cells in lines) + "\n")
    sid = source_id(archive, file)
    expect = narrative_expectations(main_rows)["narrative"]
    header = ["disease_id", "disease_name", "symptom"]
    with owner_db.transaction(None) as tx:
        tx.add(Source(source_id=sid, source_name=f"{archive}/{file}", version="t", sha256="0"))
        tx.flush()
        for number, cells in enumerate(lines, start=1):
            want = expect(dict(zip(header, cells, strict=True)))
            record_id = f"rec_{tag}_{number}"
            tx.add(
                SourceRecord(
                    record_id=record_id,
                    source_id=sid,
                    file_path=file,
                    row_number=number,
                    content_hash=_h(*cells),
                    raw_object_uri=f"zip://{archive}#{file}:row={number}",
                    quality_flags=want["flags"],
                )
            )
            if not want["text"]:
                continue
            disease_id = disease_candidate_id(want["label"])
            if tx.get(Disease, disease_id) is None:
                tx.add(Disease(disease_id=disease_id, preferred_name=norm_label(want["label"])))
            statement_id = f"st_{tag}_{number}"
            tx.add(
                Statement(
                    statement_id=statement_id, disease_id=disease_id, statement_type="symptom", text_content=cells[2]
                )
            )
            tx.flush()
            tx.add(
                StatementSource(
                    statement_id=statement_id, record_id=record_id, source_url=want["url"], text_span=want["span"]
                )
            )

    def facts_of(cur):
        with zipfile.ZipFile(path) as z:
            return verify_statement_file(cur, z, file, sid, expect)

    with scratch(os.environ["TEST_MIGRATION_DATABASE_URL"]) as cur:
        facts = facts_of(cur)
    assert facts["aligned"] and not +facts["row_diffs"]
    assert (facts["rows"], facts["links_expected"], facts["links"]) == (5, 4, 4)
    assert (facts["statements_expected"], facts["statements"], facts["changed_by_no_reviewer"]) == (4, 4, 0)
    assert (
        facts["expected_flags"]
        == facts["flags"]
        == {
            "disease_name_disagrees_with_diseases_main": 1,
            "unknown_native_disease_id": 1,
        }
    )
    assert facts["attribution_rows"] == {"source_url": 4, "column": 4, "native_id": 4}

    damage = {
        "statement text, type or disease": f"UPDATE statements SET text_content = 'changed' WHERE statement_id = 'st_{tag}_1'",
        "source url": f"UPDATE statement_sources SET source_url = 'https://example.org/other' WHERE statement_id = 'st_{tag}_1'",
        "attribution field native_id": (
            f"""UPDATE statement_sources SET text_span = '{{"column": "symptom"}}' WHERE statement_id = 'st_{tag}_1'"""
        ),
        "one statement per row with text": f"DELETE FROM statement_sources WHERE statement_id = 'st_{tag}_2'",
        "content hash": f"UPDATE source_records SET content_hash = 'x' WHERE record_id = 'rec_{tag}_3'",
    }
    for expected, statement in damage.items():
        with scratch(os.environ["TEST_MIGRATION_DATABASE_URL"]) as cur:
            cur.execute(statement)
            assert facts_of(cur)["row_diffs"][expected] == 1, expected
    with scratch(os.environ["TEST_MIGRATION_DATABASE_URL"]) as cur:
        cur.execute(f"UPDATE statements SET status = 'approved' WHERE statement_id = 'st_{tag}_1'")
        approved = facts_of(cur)
        cur.execute(f"DELETE FROM source_records WHERE record_id = 'rec_{tag}_5'")  # the row without a statement
        assert facts_of(cur)["aligned"] is False  # a missing record: rows cannot be paired
    assert approved["changed_by_no_reviewer"] == 1
    # The same approval with a reviewer's decision recorded for it is in order.
    with scratch(os.environ["TEST_MIGRATION_DATABASE_URL"]) as cur:
        cur.execute(f"UPDATE statements SET status = 'approved' WHERE statement_id = 'st_{tag}_1'")
        cur.execute(NOTE, ("statement", f"st_{tag}_1", "approved", 0))
        assert facts_of(cur)["changed_by_no_reviewer"] == 0

    # The report lines for a narrative table, with the approval nobody recorded counted as a mismatch.
    report = Report(mapping_table())
    info = {
        "entry": {"archive": "archive(13).zip", "file": "symptoms.csv"},
        "sid": sid,
        "kind": "statement",
        "facts": approved,
    }
    world = {
        "disease_cross": {},
        "reference": {"disease": {}},
        "evidence": {
            "mentions_expected": 2,
            "mentions": 2,
            "mentions_unexpected": 0,
            "mentions_changed_by_no_reviewer": 0,
        },
        "claims": {
            "statements": 4,
            "expected": 9,
            "stored_as_expected": 9,
            "unexpected": 0,
            "not_their_text": 0,
            "decided_without_reviewer": 0,
        },
    }
    _statement_file(report, world, ("archive(13).zip", "symptoms.csv"), info)
    assert _mismatches(report) == [
        "statements whose status was changed by no reviewer (imported text stays pending until reviewed)"
    ]
    # The single claims are checked since M2.6: nothing in this row is left for a later sub-step.
    assert {check.row for check in report.checks} == {12} and report.deferred == []
    # A claim that is missing, and one the rules do not make, are both mismatches.
    report = Report(mapping_table())
    world["claims"] = {**world["claims"], "stored_as_expected": 8, "unexpected": 1}
    _statement_file(report, world, ("archive(13).zip", "symptoms.csv"), info)
    assert _mismatches(report)[1:] == [
        "single claims of the symptom statements, each a span of its statement, in the review queue",
        "claims that are not their statement's text, are not made by the rules, or were decided by no reviewer",
    ]


# -- narrative text files -------------------------------------------------------------------------

DOCUMENT = """Disease : Synthetic Condition
Category: Sample Category
URL     : https://example.org/synthetic
==========
Lead paragraph alphaword about the synthetic condition.

== Signs ==
First paragraph of the section.

Second paragraph of the section.
"""


@pytest.mark.postgres
def test_text_chunks_must_reproduce_the_file_at_their_offsets(tmp_path, owner_db):
    tag = uuid.uuid4().hex[:10]
    archive, name = f"complete-texts-{tag}.zip", f"synthetic_{tag}.txt"
    document = DOCUMENT.replace("Synthetic Condition", f"Synthetic Condition {tag}")
    digest = hashlib.sha256(document.encode()).hexdigest()
    path = tmp_path / archive
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, document.encode("utf-8"))
        z.writestr(
            "diseases_main.csv",
            f"id,name,category,summary,word_count,url\nD1,Synthetic Condition {tag},Sample Category,s,1,"
            "https://example.org/synthetic\n",
        )
    manifest = Manifest({archive: sha256_file(path)}, [], [{"archive": archive, "file": name, "sha256": digest}])
    text_sid, main_sid = source_id(archive, "*.txt"), source_id(archive, "diseases_main.csv")
    with owner_db.transaction(None) as tx:
        if tx.get(MappingRelease, RELEASE_ID) is None:
            tx.add(MappingRelease(release_id=RELEASE_ID, version="lexical-0"))
        tx.add(Source(source_id=text_sid, source_name=f"{archive}/*.txt", version="t", sha256="0"))
        tx.add(Source(source_id=main_sid, source_name=f"{archive}/diseases_main.csv", version="t", sha256="0"))
        tx.flush()
        tx.add(
            SourceRecord(
                record_id=f"rec_{tag}_text",
                source_id=text_sid,
                file_path=name,
                row_number=None,
                content_hash=digest,
                raw_object_uri=f"zip://{archive}#{name}",
            )
        )
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    load_chunks(tmp_path, url, manifest, archive=archive)

    def facts_of(cur):
        with zipfile.ZipFile(path) as z:
            return verify_text_files(cur, z, manifest.text_files, text_sid, KNOWLEDGE_RELEASE_ID)

    with scratch(url) as cur:
        facts = facts_of(cur)
    assert facts["chunks_expected"] == facts["chunks"] == 2 and facts["records_with_file_digest"] == 1
    assert facts["offsets_reproduce_text"] == facts["with_attribution"] == facts["with_source_category"] == 2
    assert (facts["searchable"], facts["uncovered_characters"], facts["release_status"]) == (2, 0, "pending")
    report = Report(mapping_table())
    none = {"approved": 0, "with_their_statement": 0, "decided_without_reviewer": 0, "statements_no_part_gave": 0}
    _texts(report, {"texts": facts, "text_chunks": none})
    # Statements of the text files are made by a reviewer's approval of a part (M2.5e): nothing is left for later.
    assert _mismatches(report) == [] and report.deferred == []
    assert {check.row for check in report.checks} == {TEXT_ROW}
    # An approved part without its statement, and a statement no part gave, are mismatches.
    report = Report(mapping_table())
    _texts(report, {"texts": facts, "text_chunks": {**none, "approved": 2, "with_their_statement": 1}})
    assert _mismatches(report) == [
        "parts of the text files approved by a reviewer, each with the statement made from it"
    ]
    report = Report(mapping_table())
    _texts(report, {"texts": facts, "text_chunks": {**none, "statements_no_part_gave": 1}})
    assert _mismatches(report) == [
        "statements of the text files that no reviewed part gave, or parts decided by no reviewer"
    ]

    with scratch(url) as cur:
        cur.execute(
            "UPDATE evidence_chunks SET chunk_text = chunk_text || ' added' WHERE record_id = %s", (f"rec_{tag}_text",)
        )
        cur.execute("UPDATE source_records SET content_hash = 'x' WHERE record_id = %s", (f"rec_{tag}_text",))
        damaged = facts_of(cur)
    assert damaged["offsets_reproduce_text"] == 0 and damaged["records_with_file_digest"] == 0
    report = Report(mapping_table())
    _texts(report, {"texts": damaged, "text_chunks": none})
    assert _mismatches(report) == [
        "text files registered as records with the file's SHA-256",
        "chunks whose stored character offsets reproduce their text from the file",
    ]


def test_a_file_the_mapping_table_does_not_name_has_no_rows():
    assert completeness_cases.roles_of({"archive": "unknown.zip", "file": "x.csv", "adapter": "symptom_list"}) == {}


@pytest.mark.postgres
def test_a_row_a_reviewer_decided_is_in_order_and_a_row_changed_by_nobody_is_reported(matrix, owner_db):
    """M2.5d1. The check used to report every row that was not pending (BUG-021)."""
    _register_label_mappings(owner_db, matrix)
    train = source_id(matrix["archive"], "train.csv")
    tag = matrix["release"].removeprefix("rel-")
    flu, cold = disease_candidate_id("Flu"), disease_candidate_id("Cold")
    with scratch(matrix["url"]) as cur:
        cur.execute(
            "SELECT mapping_id FROM disease_mappings WHERE release_id = %s AND source_id = %s AND original_label = 'Flu'",
            (matrix["release"], train),
        )
        label_mapping = cur.fetchone()[0]
        cur.execute(
            "SELECT min(evidence_id) FROM disease_feature_evidence WHERE record_id = %s", (whole_file_record_id(train),)
        )
        proposal = cur.fetchone()[0]
    rows = {  # review target type -> table, key column, status column, key
        "source": ("sources", "source_id", "provenance_status", train),
        "disease": ("diseases", "disease_id", "status", flu),
        "disease_mapping": ("disease_mappings", "mapping_id", "status", label_mapping),
        "feature": ("features", "feature_id", "status", f"feat_{tag}_f1"),
        "feature_mapping": ("feature_mappings", "mapping_id", "status", f"fm_{tag}_tr_4"),
        "evidence": ("disease_feature_evidence", "evidence_id", "status", proposal),
    }

    def reported(cur):
        return [measure for measure in _mismatches(_case_report(cur, matrix)[0]) if not measure.endswith(STATED)]

    def by_nobody(cur):
        return any("changed by no reviewer" in measure for measure in reported(cur))

    for target, (table, key, status, value) in rows.items():
        change = f"UPDATE {table} SET {status} = %s WHERE {key} = %s"
        with scratch(matrix["url"]) as cur:
            cur.execute(change, ("approved", value))
            assert cur.rowcount == 1, target
            assert by_nobody(cur), f"an approved {target} with no decision behind it was not reported"
            cur.execute(NOTE, (target, value, "approved", 0))
            assert reported(cur) == [], f"an approved {target} with its decision recorded was reported"
        with scratch(matrix["url"]) as cur:
            # The last recorded decision is the one that counts: approved an hour ago, rejected since.
            cur.execute(NOTE, (target, value, "approved", 1))
            cur.execute(NOTE, (target, value, "rejected", 0))
            cur.execute(change, ("approved", value))
            assert by_nobody(cur), f"a {target} whose status is not its last decision was not reported"
            cur.execute(change, ("rejected", value))
            assert reported(cur) == [], target
    # A label merged into another was retired by the merge, which the history records with the reviewer's name.
    with scratch(matrix["url"]) as cur:
        cur.execute("UPDATE diseases SET status = 'retired', redirected_to = %s WHERE disease_id = %s", (cold, flu))
        assert by_nobody(cur)
        cur.execute(
            "INSERT INTO disease_history (event_id, action, disease_id, other_id, reviewer, note) "
            "VALUES (gen_random_uuid(), 'merge', %s, %s, 'dev-reviewer:test', 'They name the same thing.')",
            (flu, cold),
        )
        assert reported(cur) == []
    with scratch(matrix["url"]) as cur:  # every change above was rolled back
        assert reported(cur) == []
