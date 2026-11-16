"""Positional source audit. Streams every CSV once and reproduces the handoff's measured
inventory (`data_audit/audit.json`) and the manifest's expectations. Counts are sample
counts of rows in files: not patients, not prevalence."""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from .archives import RAW_DIR, ROOT, Manifest, load_manifest, read_csv_positional, verify_all

REFERENCE_AUDIT = ROOT / "data_audit" / "audit.json"
DISEASE_HEADERS = ("disease", "diseases", "name", "disease_name")


def norm_label(value: str) -> str:
    """casefold + strip + collapse whitespace. Lexical only; no synonym merging."""
    return " ".join(value.strip().casefold().split())


def _digest(cells: list[str]) -> bytes:
    return hashlib.blake2b("\x1f".join(cells).encode("utf-8", "surrogatepass"), digest_size=16).digest()


def audit_csv(archive: zipfile.ZipFile, archive_name: str, member: str) -> tuple[dict[str, Any], set[str], set[bytes]]:
    header, rows = read_csv_positional(archive, member)
    disease_index = next(i for i, c in enumerate(header) if c.lower() in DISEASE_HEADERS)
    id_columns = {i for i, c in enumerate(header) if c.lower() == "patient_id"}
    sex_index = next((i for i, c in enumerate(header) if c.lower() in ("sex", "gender")), None)
    repeated = {name: [i for i, c in enumerate(header) if c == name] for name, n in Counter(header).items() if n > 1}
    exact: set[bytes] = set()
    profiles: set[bytes] = set()
    labels: set[str] = set()
    sexes: Counter[str] = Counter()
    conflicts: Counter[str] = Counter()
    count = malformed = 0
    width = len(header)
    for row in rows:
        count += 1
        if len(row) != width:
            malformed += 1
            continue
        exact.add(_digest(row))
        profiles.add(_digest([v for i, v in enumerate(row) if i not in id_columns]) if id_columns else _digest(row))
        labels.add(row[disease_index])
        if sex_index is not None:
            sexes[row[sex_index]] += 1
        for name, positions in repeated.items():
            first = row[positions[0]]
            if any(row[i] != first for i in positions[1:]):
                conflicts[name] += 1
    record = {
        "archive": archive_name,
        "file": member,
        "rows": count,
        "columns": width,
        "disease_labels": len(labels),
        "exact_unique_rows": len(exact),
        "exact_duplicate_rows": count - malformed - len(exact),
        "unique_profiles_excluding_patient_id": len(profiles),
        "repeated_profiles_excluding_patient_id": count - malformed - len(profiles),
        "malformed_rows": malformed,
        "sex_counts": dict(sexes),
        "duplicate_header_count": len(repeated),
        "duplicate_column_disagreement_rows": dict(conflicts),
        "repeated_header_positions": repeated,
    }
    return record, {norm_label(v) for v in labels}, profiles


def run_audit(raw_dir: Path = RAW_DIR, manifest: Manifest | None = None) -> dict[str, Any]:
    manifest = manifest or load_manifest()
    entries = verify_all(raw_dir, manifest)
    files: list[dict[str, Any]] = []
    texts: list[dict[str, str]] = []
    label_sets: dict[str, set[str]] = {}
    profiles15: dict[str, set[bytes]] = {}
    for archive_name in manifest.archives:
        label_sets[archive_name] = set()
        with zipfile.ZipFile(raw_dir / archive_name) as archive:
            for info in entries[archive_name]:
                if info.is_dir():
                    continue
                if info.filename.lower().endswith(".csv"):
                    record, labels, profiles = audit_csv(archive, archive_name, info.filename)
                    files.append(record)
                    label_sets[archive_name] |= labels
                    if archive_name == "archive(15).zip":
                        profiles15[info.filename] = profiles
                else:
                    texts.append(
                        {
                            "archive": archive_name,
                            "file": info.filename,
                            "sha256": hashlib.sha256(archive.read(info)).hexdigest(),
                        }
                    )
    names = list(label_sets)
    return {
        "union_lexical_disease_labels": len(set().union(*label_sets.values())),
        "files": files,
        "text_files": texts,
        "overlap": [
            {"archive_a": a, "archive_b": b, "shared_lexical_labels": len(label_sets[a] & label_sets[b])}
            for a in names
            for b in names
            if a < b
        ],
        "archive15_train_test_shared_profiles_excluding_patient_id": len(
            profiles15.get("train.csv", set()) & profiles15.get("test.csv", set())
        ),
    }


def compare(
    result: dict[str, Any], manifest: Manifest | None = None, reference_path: Path = REFERENCE_AUDIT
) -> list[str]:
    """Differences between this run and the handoff's manifest and measured audit. Empty = reproduced."""
    manifest = manifest or load_manifest()
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    diffs: list[str] = []
    got = {(f["archive"], f["file"]): f for f in result["files"]}
    for expected in manifest.files:
        key = (expected["archive"], expected["file"])
        if key not in got:
            diffs.append(f"missing CSV {key}")
            continue
        for field, mine in (
            ("expected_rows", "rows"),
            ("expected_columns", "columns"),
            ("exact_unique_rows", "exact_unique_rows"),
        ):
            if got[key][mine] != expected[field]:
                diffs.append(f"{key} {mine}: {got[key][mine]} != manifest {expected[field]}")
    if len(got) != len(manifest.files):
        diffs.append(f"{len(got)} CSV files found, manifest lists {len(manifest.files)}")
    got_text = {(t["archive"], t["file"]): t["sha256"] for t in result["text_files"]}
    want_text = {(t["archive"], t["file"]): t["sha256"] for t in manifest.text_files}
    if got_text != want_text:
        changed = sorted(k for k in set(got_text) | set(want_text) if got_text.get(k) != want_text.get(k))
        diffs.append(f"text files differ from manifest: {changed[:5]} ({len(changed)} total)")
    for ref in reference["files"]:
        mine = got.get((ref["archive"], ref["file"]), {})
        for field, value in ref.items():
            if field not in ("archive", "file") and mine.get(field) != value:
                diffs.append(f"({ref['archive']}, {ref['file']}) {field}: {mine.get(field)} != audit.json {value}")
    for field in (
        "union_lexical_disease_labels",
        "overlap",
        "archive15_train_test_shared_profiles_excluding_patient_id",
    ):
        if result[field] != reference[field]:
            diffs.append(f"{field}: {result[field]} != audit.json {reference[field]}")
    return diffs
