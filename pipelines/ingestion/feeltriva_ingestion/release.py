"""A source release supplied after the handoff: the dataset archive 15 comes from (M2.12).

The owner supplied the publisher's release of the DDXPlus dataset. This module

- checks the supplied file against its registered checksum and member list;
- traces every row of the archive-15 files to a row of the release, so that the origin is
  established from the data and not from a resemblance;
- stores the publisher's question dictionary on the archive-15 column mappings: the full
  question text, whether the publisher calls it a symptom or an antecedent, the answer type and
  the default answer.

What the publisher says about the release (licence, how the patients were produced) is kept in
`specs/supplementary_sources.json` and recorded on the sources. Nothing is approved. Counts are
counts of rows in files.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from feeltriva_api.settings import Settings
from sqlalchemy import create_engine

from .archives import RAW_DIR, ROOT, ArchiveError, read_csv_positional, sha256_file
from .cases import _raw_cursor
from .load import RELEASE_ID, source_id
from .verify_files import role_positions

SUPPLEMENTARY_PATH = ROOT / "specs" / "supplementary_sources.json"
SPLITS = ("train", "validate", "test")
MEMBERS = {"release_evidences.json", "release_conditions.json", *(f"release_{s}_patients.zip" for s in SPLITS)}
MAX_MEMBER_BYTES = 2 * 1024 * 1024 * 1024
_CODE = re.compile(r"^(E_\d+)_(.*)$")


def load_supplementary(path: Path = SUPPLEMENTARY_PATH) -> list[dict[str, Any]]:
    return list(json.loads(path.read_text(encoding="utf-8"))["sources"])


def open_release(raw_dir: Path, entry: dict[str, Any]) -> zipfile.ZipFile:
    """The supplied file, after its checksum and its member list have been checked."""
    path = raw_dir / entry["name"]
    if not path.is_file():
        raise ArchiveError(f"{entry['name']}: missing from {raw_dir}")
    digest = sha256_file(path)
    if digest != entry["sha256"]:
        raise ArchiveError(f"{entry['name']}: SHA-256 {digest} does not match the registered {entry['sha256']}")
    release = zipfile.ZipFile(path)
    names = {info.filename for info in release.infolist()}
    if names != MEMBERS or any(info.file_size > MAX_MEMBER_BYTES for info in release.infolist()):
        release.close()
        raise ArchiveError(f"{entry['name']}: unexpected contents {sorted(names ^ MEMBERS)}")
    return release


def read_dictionary(release: zipfile.ZipFile) -> dict[str, dict[str, Any]]:
    """The publisher's description of every question, by its code (`E_91`)."""
    return dict(json.loads(release.read("release_evidences.json")))


def _answered(evidences: str) -> frozenset[str]:
    """Question codes in a patient's evidence list: "['E_48', 'E_54_@_V_161']" -> {E_48, E_54}."""
    return frozenset(item.strip(" '\"").split("_@_")[0] for item in evidences.strip("[]").split(",") if item.strip())


def release_keys(release: zipfile.ZipFile, split: str) -> list[int]:
    """One number per patient of a release split: age, sex, condition and the set of answered questions."""
    with zipfile.ZipFile(io.BytesIO(release.read(f"release_{split}_patients.zip"))) as inner:
        member = inner.infolist()[0]
        if member.file_size > MAX_MEMBER_BYTES:
            raise ArchiveError(f"release {split} patients: {member.file_size} bytes is over the limit")
        with inner.open(member) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
            at = {name: i for i, name in enumerate(next(reader))}
            age, sex, condition, evidences = at["AGE"], at["SEX"], at["PATHOLOGY"], at["EVIDENCES"]
            return [hash((row[age], row[sex], row[condition], _answered(row[evidences]))) for row in reader]


def file_keys(archive: zipfile.ZipFile, file: str) -> list[int]:
    """The same number for every row of one of our files, whose question columns are 0/1."""
    header, reader = read_csv_positional(archive, file)
    roles = role_positions(header)
    age, sex, condition = roles["age"], roles["demographic"], roles["label"]
    codes = [(i, match.group(1)) for i, name in enumerate(header) if (match := _CODE.match(name))]
    width = len(header)
    return [
        hash((row[age], row[sex], row[condition], frozenset(code for i, code in codes if row[i] == "1")))
        for row in reader
        if len(row) == width
    ]


def trace(ours: list[int], release: dict[str, list[int]]) -> dict[str, Any]:
    """Which rows of the release our rows are, as runs in file order.

    Returns the runs (our first row, release split, its first row, length; rows counted from 1)
    and how many of our rows are found nowhere in the release."""
    index: dict[int, list[tuple[str, int]]] = {}
    for split, keys in release.items():
        for position, key in enumerate(keys):
            index.setdefault(key, []).append((split, position))
    runs: list[dict[str, Any]] = []
    unmatched = i = 0
    while i < len(ours):
        best: tuple[int, str, int] = (0, "", 0)
        for split, position in index.get(ours[i], ())[:50]:
            keys, length = release[split], 0
            while (
                i + length < len(ours) and position + length < len(keys) and ours[i + length] == keys[position + length]
            ):
                length += 1
            if length > best[0]:
                best = (length, split, position)
        if best[0] == 0:
            unmatched += 1
            i += 1
            continue
        runs.append(
            {"our_first_row": i + 1, "release_split": best[1], "release_first_row": best[2] + 1, "rows": best[0]}
        )
        i += best[0]
    return {"rows": len(ours), "traced": len(ours) - unmatched, "not_in_release": unmatched, "runs": runs}


def _words(text: str) -> str:
    return "_".join(re.sub(r"[^a-z0-9\s]", "", text.lower()).split())


def heading_is_start_of(heading: str, question: str) -> bool:
    """Is our cut-off column heading the beginning of the publisher's question?"""
    match = _CODE.match(heading)
    return match is not None and _words(question).startswith(match.group(2).lower())


def dictionary_entry(code: str, entry: dict[str, Any], doi: str) -> dict[str, Any]:
    """What is kept on a column mapping from the publisher's dictionary."""
    kept: dict[str, Any] = {
        "release": doi,
        "code": code,
        "question": entry["question_en"],
        "is_antecedent": bool(entry["is_antecedent"]),
        "answer_type": {"B": "yes_no", "C": "one_of_several", "M": "several_of_several"}.get(
            entry["data_type"], "unknown"
        ),
        "default_value": entry["default_value"],
    }
    meanings = entry.get("value_meaning") or {}
    if meanings:
        kept["values"] = {value: (texts or {}).get("en", "") for value, texts in meanings.items()}
    elif entry.get("possible-values"):
        kept["values"] = {str(value): "" for value in entry["possible-values"]}
    return kept


def load_release(
    raw_dir: Path = RAW_DIR,
    database_url: str | None = None,
    entries: list[dict[str, Any]] | None = None,
    release_id: str = RELEASE_ID,
) -> dict[str, Any]:
    """Trace the described files to the release and store the dictionary on their mappings."""
    if database_url is None:
        app = Settings()
        database_url = app.migration_database_url or app.database_url
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL (or DATABASE_URL) is required")
    entries = load_supplementary() if entries is None else entries
    result: dict[str, Any] = {"releases": {}}
    engine = create_engine(database_url)
    try:
        for entry in (e for e in entries if e.get("kind") == "ddxplus_release"):
            with open_release(raw_dir, entry) as release:
                dictionary = read_dictionary(release)
                conditions = json.loads(release.read("release_conditions.json"))
                keys = {split: release_keys(release, split) for split in SPLITS}
            facts: dict[str, Any] = {
                "questions": len(dictionary),
                "conditions": len(conditions),
                "answer_types": {},
                "antecedents": sum(1 for e in dictionary.values() if e["is_antecedent"]),
                "release_rows": {split: len(found) for split, found in keys.items()},
                "files": {},
                "changed": {"mappings": 0, "sources": 0},
            }
            for e in dictionary.values():
                facts["answer_types"][e["data_type"]] = facts["answer_types"].get(e["data_type"], 0) + 1
            release_sid = source_id(entry["name"], "*")
            with _raw_cursor(engine) as cur:
                cur.execute(
                    """INSERT INTO sources (source_id, source_name, version, origin_url, licence, sha256, provenance_status)
                       VALUES (%s, %s, %s, %s, %s, %s, 'pending') ON CONFLICT DO NOTHING""",
                    (
                        release_sid,
                        f"{entry['name']} ({entry['title']})",
                        entry["doi"],
                        entry["origin_url"],
                        entry["licence"],
                        entry["sha256"],
                    ),
                )
                facts["changed"]["sources"] += cur.rowcount
                for described in entry["describes"]:
                    archive_name, file = described["archive"], described["file"]
                    sid = source_id(archive_name, file)
                    with zipfile.ZipFile(raw_dir / archive_name) as archive:
                        traced = trace(file_keys(archive, file), keys)
                        header, _ = read_csv_positional(archive, file)
                    origin = {
                        "origin": {
                            "release": entry["title"],
                            "doi": entry["doi"],
                            "licence": entry["licence"],
                            "publisher_statement": entry["publisher_statement"],
                            "rows": traced["rows"],
                            "rows_traced_to_the_release": traced["traced"],
                            "runs": traced["runs"][:50],
                        }
                    }
                    value = json.dumps(origin, sort_keys=True)
                    cur.execute(
                        """UPDATE sources SET origin_url = %s, licence = %s, population = population || %s::jsonb
                           WHERE source_id = %s AND provenance_status = 'pending'
                             AND (origin_url IS DISTINCT FROM %s OR licence IS DISTINCT FROM %s OR NOT population @> %s::jsonb)""",
                        (
                            entry["origin_url"],
                            entry["licence"],
                            value,
                            sid,
                            entry["origin_url"],
                            entry["licence"],
                            value,
                        ),
                    )
                    facts["changed"]["sources"] += cur.rowcount
                    cur.execute(
                        "SELECT mapping_id, original_term FROM feature_mappings WHERE source_id = %s AND release_id = %s "
                        "AND column_index IS NOT NULL",
                        (sid, release_id),
                    )
                    mapped = cur.fetchall()
                    matched = starts = 0
                    for mapping_id, heading in mapped:
                        match = _CODE.match(heading)
                        if match is None or match.group(1) not in dictionary:
                            continue
                        code = match.group(1)
                        matched += 1
                        starts += heading_is_start_of(heading, dictionary[code]["question_en"])
                        kept = json.dumps(dictionary_entry(code, dictionary[code], entry["doi"]), sort_keys=True)
                        cur.execute(
                            """UPDATE feature_mappings SET transformation = jsonb_set(transformation, '{source_dictionary}', %s::jsonb, true)
                               WHERE mapping_id = %s AND status = 'pending'
                                 AND transformation -> 'source_dictionary' IS DISTINCT FROM %s::jsonb""",
                            (kept, mapping_id, kept),
                        )
                        facts["changed"]["mappings"] += cur.rowcount
                    facts["files"][f"{archive_name}/{file}"] = {
                        **traced,
                        "question_columns": len([name for name in header if _CODE.match(name)]),
                        "mappings": len(mapped),
                        "mappings_with_a_dictionary_entry": matched,
                        "headings_that_start_the_question": starts,
                    }
            result["releases"][entry["name"]] = facts
    finally:
        engine.dispose()
    return result


def check(result: dict[str, Any]) -> list[str]:
    """What must hold for the origin to count as established. Empty = consistent."""
    diffs = []
    for name, facts in result["releases"].items():
        for file, found in facts["files"].items():
            if found["not_in_release"]:
                diffs.append(f"{file}: {found['not_in_release']} rows are not in {name}")
            if found["mappings_with_a_dictionary_entry"] != found["mappings"]:
                diffs.append(
                    f"{file}: {found['mappings_with_a_dictionary_entry']} of {found['mappings']} columns are in the dictionary"
                )
            if found["headings_that_start_the_question"] != found["mappings"]:
                diffs.append(
                    f"{file}: {found['headings_that_start_the_question']} of {found['mappings']} headings start their question"
                )
    return diffs
