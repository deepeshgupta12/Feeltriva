"""A source file whose columns changed (schema drift) is refused by every loader that reads it.

The handoff asks for this in two places: `docs/05` M1 ("quality flags for count mismatches,
invalid joins and schema changes") and the ingestion test list ("... idempotent rerun, schema
drift"). Per loader:

- reference / narrative loader (`load`): this file, with the real archives
- case loader (`load-cases`) and symptom-list loader (`load-lists`): this file
- matrix loader (`load-features`): `test_features.py::test_schema_drift_stops_the_load`
- text loader (`load-chunks`): `test_chunks.py::test_tampered_file_and_missing_records_are_refused`
- the completeness check: `test_completeness.py::test_a_file_whose_columns_changed_is_reported_and_not_compared`

The evidence loader reads only the database and the archive store reads only bytes, so neither
has columns to drift.
"""

from __future__ import annotations

import os
import uuid
import zipfile

import pytest
from feeltriva_api.models import MappingRelease, Source
from feeltriva_ingestion.archives import ArchiveError, Manifest, load_manifest, require_layout, sha256_file
from feeltriva_ingestion.cases import load_cases
from feeltriva_ingestion.lists import load_symptom_lists
from feeltriva_ingestion.load import RELEASE_ID, source_id
from sqlalchemy import text

TARGETS = ["source_records", "dataset_cases", "case_labels"]
ENTRY = {"archive": "a.zip", "file": "f.csv", "expected_columns": 3}


def test_layout_guard_accepts_the_registered_columns():
    require_layout(["Disease", "f1", "f2"], ENTRY, any_of=(("disease", "diseases"),), named=("f1",))
    require_layout(["anything"], {"archive": "a.zip", "file": "f.csv"})  # nothing registered: nothing to compare


def test_layout_guard_refuses_a_changed_number_of_columns():
    with pytest.raises(ArchiveError, match=r"a.zip/f.csv: the file has 4 columns but 3 are registered .*schema drift"):
        require_layout(["Disease", "f1", "f2", "new"], ENTRY)


def test_layout_guard_refuses_a_missing_or_renamed_column():
    with pytest.raises(ArchiveError, match=r"column\(s\) disease / diseases not found .*schema drift"):
        require_layout(["Illness", "f1", "f2"], ENTRY, any_of=(("disease", "diseases"),))
    with pytest.raises(ArchiveError, match=r"column\(s\) Source_URL not found"):
        require_layout(["Disease", "Description", "source_url"], ENTRY, named=("Disease", "Source_URL"))


def _archive(tmp_path, owner_db, content, adapter, columns):
    tag = uuid.uuid4().hex[:10]
    archive, file = f"drift-{tag}.zip", "cases.csv"
    path = tmp_path / archive
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(file, content)
    entry = {"archive": archive, "file": file, "expected_rows": 1, "exact_unique_rows": 1, "expected_columns": columns}
    manifest = Manifest({archive: sha256_file(path)}, [{**entry, "adapter": adapter, "targets": TARGETS}], [])
    sid = source_id(archive, file)
    with owner_db.transaction(None) as tx:
        if tx.get(MappingRelease, RELEASE_ID) is None:
            tx.add(MappingRelease(release_id=RELEASE_ID, version="lexical-0"))
        tx.add(Source(source_id=sid, source_name=f"{archive}/{file}", version="t", sha256="0"))
    return manifest, sid


def _records(owner_db, sid):
    with owner_db.transaction(None) as tx:
        return tx.execute(text("SELECT count(*) FROM source_records WHERE source_id = :s"), {"s": sid}).scalar_one()


@pytest.mark.postgres
@pytest.mark.parametrize(
    ("content", "columns", "message"),
    [
        ("PATIENT_ID,AGE,SEX,DISEASE,f1,added\n1,30,F,Flu,1,0\n", 5, "6 columns but 5 are registered"),  # column added
        ("PATIENT_ID,AGE,SEX,DISEASE\n1,30,F,Flu\n", 5, "4 columns but 5 are registered"),  # column removed
        ("PATIENT_ID,AGE,SEX,ILLNESS,f1\n1,30,F,Flu,1\n", 5, "disease / diseases"),  # label column renamed
    ],
)
def test_case_loader_refuses_a_file_whose_columns_changed(tmp_path, owner_db, content, columns, message):
    manifest, sid = _archive(tmp_path, owner_db, content, "positional_feature_matrix", columns)
    with pytest.raises(ArchiveError, match=message):
        load_cases(tmp_path, os.environ["TEST_MIGRATION_DATABASE_URL"], manifest)
    assert _records(owner_db, sid) == 0  # nothing was loaded


@pytest.mark.postgres
def test_list_loader_refuses_a_file_without_its_list_column(tmp_path, owner_db):
    content = 'Patient_ID,Age,Gender,Complaints,Symptom_Count,Disease\n1,30,Male,"fever, cough",2,Flu\n'
    manifest, sid = _archive(tmp_path, owner_db, content, "symptom_list", 6)
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    load_cases(tmp_path, url, manifest)  # the label column is still there, so the row itself loads
    with pytest.raises(ArchiveError, match="symptom_text / symptoms not found"):
        load_symptom_lists(tmp_path, url, manifest)
    with owner_db.transaction(None) as tx:
        mappings = tx.execute(
            text("SELECT count(*) FROM feature_mappings WHERE source_id = :s"), {"s": sid}
        ).scalar_one()
    assert mappings == 0  # no list term was registered


@pytest.mark.postgres
@pytest.mark.archives
@pytest.mark.parametrize(
    ("file", "change", "message"),
    [
        ("causes.csv", {"expected_columns": 4}, "3 columns but 4 are registered"),
        ("symptom_Description_820_verified_v5.csv", {"adapter": "disease_metadata"}, r"column\(s\) id, name"),
    ],
)
def test_reference_loader_refuses_a_file_that_differs_from_its_registered_layout(
    owner_db, monkeypatch, file, change, message
):
    """The real file is unchanged; the registered layout is made to differ from it, which is
    the same situation as a new file arriving under an old registration."""
    from feeltriva_ingestion import load

    real = load_manifest()
    drifted = Manifest(
        real.archives, [{**f, **change} if f["file"] == file else f for f in real.files], real.text_files
    )
    monkeypatch.setattr(load, "load_manifest", lambda: drifted)

    def counts():
        with owner_db.transaction(None) as tx:
            return tuple(
                tx.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()  # noqa: S608 - fixed table names
                for table in ("sources", "source_records", "statements", "disease_mappings", "feature_mappings")
            )

    before = counts()
    with pytest.raises(ArchiveError, match=message):
        load.load_reference(database_url=os.environ["TEST_MIGRATION_DATABASE_URL"])
    assert counts() == before  # refused before anything was written
