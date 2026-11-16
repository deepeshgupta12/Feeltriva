"""ZIP safety, checksum and positional-reading behaviour on small crafted archives."""

from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest
from feeltriva_ingestion import archives
from feeltriva_ingestion.archives import ArchiveError, Manifest, read_csv_positional, validate_zip, verify_all
from feeltriva_ingestion.audit import audit_csv, norm_label


def _zip(path: Path, entries: dict[str, bytes], compression: int = zipfile.ZIP_DEFLATED) -> Path:
    with zipfile.ZipFile(path, "w", compression) as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return path


def test_well_formed_archive_passes(tmp_path):
    infos = validate_zip(_zip(tmp_path / "ok.zip", {"data.csv": b"a,b\n1,2\n", "notes.txt": b"text"}))
    assert [i.filename for i in infos] == ["data.csv", "notes.txt"]


@pytest.mark.parametrize(
    "name", ["../escape.csv", "a/../../escape.csv", "/etc/passwd.csv", "C:/windows/x.csv", "..\\escape.csv"]
)
def test_path_traversal_and_absolute_paths_are_rejected(tmp_path, name):
    with pytest.raises(ArchiveError, match="unsafe entry path"):
        validate_zip(_zip(tmp_path / "bad.zip", {name: b"a\n1\n"}))


@pytest.mark.parametrize("name", ["run.sh", "payload.exe", "data.csv.py", "macro.xlsm", "noextension"])
def test_unexpected_content_types_are_rejected(tmp_path, name):
    with pytest.raises(ArchiveError, match="not allowed"):
        validate_zip(_zip(tmp_path / "bad.zip", {name: b"x"}))


def test_symbolic_link_entries_are_rejected(tmp_path):
    path = tmp_path / "link.zip"
    with zipfile.ZipFile(path, "w") as z:
        info = zipfile.ZipInfo("link.csv")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(info, "/etc/passwd")
    with pytest.raises(ArchiveError, match="symbolic link"):
        validate_zip(path)


def test_decompression_bomb_is_rejected_by_ratio(tmp_path):
    bomb = _zip(tmp_path / "bomb.zip", {"zeros.csv": b"0" * (20 * 1024 * 1024)})
    assert bomb.stat().st_size < 100 * 1024
    with pytest.raises(ArchiveError, match="compression ratio"):
        validate_zip(bomb)


def test_size_and_entry_count_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(archives, "MAX_ENTRY_BYTES", 10)
    with pytest.raises(ArchiveError, match="over the limit"):
        validate_zip(_zip(tmp_path / "big.zip", {"a.csv": b"x" * 11}, zipfile.ZIP_STORED))
    monkeypatch.setattr(archives, "MAX_ENTRY_BYTES", 100)
    monkeypatch.setattr(archives, "MAX_TOTAL_BYTES", 15)
    with pytest.raises(ArchiveError, match="exceeds the limit"):
        validate_zip(_zip(tmp_path / "total.zip", {"a.csv": b"x" * 10, "b.csv": b"y" * 10}, zipfile.ZIP_STORED))
    monkeypatch.setattr(archives, "MAX_ENTRIES", 2)
    with pytest.raises(ArchiveError, match="entries exceeds"):
        validate_zip(_zip(tmp_path / "many.zip", {f"{i}.csv": b"x" for i in range(3)}))


def test_not_a_zip_and_missing_archive(tmp_path):
    (tmp_path / "fake.zip").write_bytes(b"this is not a zip")
    with pytest.raises(ArchiveError, match="not a valid ZIP"):
        validate_zip(tmp_path / "fake.zip")
    with pytest.raises(ArchiveError, match="missing"):
        verify_all(tmp_path, Manifest({"absent.zip": "0" * 64}, [], []))


def test_checksum_mismatch_stops_before_any_entry_is_read(tmp_path):
    path = _zip(tmp_path / "a.zip", {"data.csv": b"a\n1\n"})
    good = archives.sha256_file(path)
    assert set(verify_all(tmp_path, Manifest({"a.zip": good}, [], []))) == {"a.zip"}
    with path.open("ab") as handle:  # tamper
        handle.write(b"\x00")
    with pytest.raises(ArchiveError, match="does not match manifest"):
        verify_all(tmp_path, Manifest({"a.zip": good}, [], []))


CSV = (
    "\ufeffdisease,fever,cough,fever,Patient_ID\n"  # BOM, repeated header 'fever'
    "Flu,1,0,1,p1\n"
    "Flu,1,0,0,p2\n"  # the two 'fever' columns disagree
    "  FLU  ,0,1,0,p3\n"
    "Flu,1,0,1,p4\n"  # same profile as p1, different patient id
    "Flu,1,0,1,p1\n"  # exact duplicate of row 1
    "Dengue fièvre,0,0,0,p5\n"  # non-ASCII label
    "short,row\n"
)  # malformed: wrong width


def test_positional_reader_keeps_repeated_headers_as_separate_columns(tmp_path):
    path = _zip(tmp_path / "m.zip", {"m.csv": CSV.encode("utf-8")})
    with zipfile.ZipFile(path) as z:
        header, rows = read_csv_positional(z, "m.csv")
        assert header == ["disease", "fever", "cough", "fever", "Patient_ID"]  # BOM stripped, both 'fever' kept
        first = next(rows)
        assert (first[1], first[3]) == ("1", "1") and len(first) == 5


def test_audit_counts_duplicates_profiles_conflicts_and_malformed_rows(tmp_path):
    path = _zip(tmp_path / "m.zip", {"m.csv": CSV.encode("utf-8")})
    with zipfile.ZipFile(path) as z:
        record, labels, _ = audit_csv(z, "m.zip", "m.csv")
    assert record["rows"] == 7 and record["columns"] == 5 and record["malformed_rows"] == 1
    assert record["exact_unique_rows"] == 5 and record["exact_duplicate_rows"] == 1
    assert record["unique_profiles_excluding_patient_id"] == 4
    assert record["repeated_profiles_excluding_patient_id"] == 2
    assert record["duplicate_header_count"] == 1
    assert record["duplicate_column_disagreement_rows"] == {"fever": 1}  # kept as a conflict, never OR-ed
    assert record["repeated_header_positions"] == {"fever": [1, 3]}
    assert record["disease_labels"] == 3 and labels == {"flu", "dengue fièvre"}  # raw labels kept; lexical groups


def test_label_normalisation_is_lexical_only():
    assert norm_label("  Type  2\tDiabetes ") == "type 2 diabetes"
    assert norm_label("Diabetes type 2") != norm_label("Type 2 diabetes")  # no semantic merging
    assert norm_label("STRASSE") == norm_label("straße")  # casefold


def test_reader_refuses_more_data_than_declared(tmp_path):
    path = _zip(tmp_path / "m.zip", {"m.csv": b"a,b\n" + b"1,2\n" * 1000})
    with zipfile.ZipFile(path) as z:
        z.getinfo("m.csv").file_size = 10  # lie about the size
        with pytest.raises(Exception, match="declared size|Bad CRC|file size"):
            header, rows = read_csv_positional(z, "m.csv")
            list(rows)
