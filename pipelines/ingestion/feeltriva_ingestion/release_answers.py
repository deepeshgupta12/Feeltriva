"""The answers behind the 0/1 of archive 15, for its questions that are not yes/no (M2.13a).

Archive 15 is a 0/1 rendering of the DDXPlus release (M2.12). For 15 of its 223 questions the
publisher records an answer that is not yes or no: where a pain is, how strong it is from 0 to
10, which region was travelled to. In the archive such a column is 1 whenever an answer is
listed, and the answer can be the publisher's "nowhere", "N" or 0. Without the answer the 1
cannot be read.

This module reads each release row our rows were traced to and stores its answers to those
questions in `case_answers`, as the release writes them, with the split and row they come from.
The archive's own 0/1 values in `case_features` are not touched.

No gaps, checked against the files themselves: every 1 in one of these columns of our file
has at least one answer in its release row, no answer exists without that 1, and every answer
is one the publisher's dictionary lists as possible. The command fails otherwise.

The patients of this release are simulated (decision E55); so are these answers.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from typing import Any

from feeltriva_api.settings import Settings
from sqlalchemy import create_engine

from .archives import RAW_DIR, ArchiveError, read_csv_positional
from .cases import _raw_cursor
from .load import source_id
from .release import (
    _CODE,
    MAX_MEMBER_BYTES,
    SPLITS,
    file_keys,
    load_supplementary,
    open_release,
    read_dictionary,
    release_keys,
    trace,
)

_COLUMNS = ("case_id", "mapping_id", "answer", "release_split", "release_row")


def answers_in(evidences: str, wanted: frozenset[str]) -> list[tuple[str, str]]:
    """(question code, answer as written) for the wanted questions of one patient's evidence list.

    "['E_48', 'E_54_@_V_161', 'E_56_@_6']" with wanted {E_54, E_56} -> [(E_54, V_161), (E_56, 6)]."""
    found = []
    for item in evidences.strip("[]").split(","):
        code, _, answer = item.strip(" '\"").partition("_@_")
        if answer and code in wanted:
            found.append((code, answer))
    return found


def _affirmed(archive: zipfile.ZipFile, file: str, wanted: frozenset[str]) -> list[frozenset[str]]:
    """For every row of one of our files, which of the wanted question columns hold a 1."""
    header, reader = read_csv_positional(archive, file)
    columns = [
        (i, match.group(1))
        for i, name in enumerate(header)
        if (match := _CODE.match(name)) and match.group(1) in wanted
    ]
    width = len(header)
    return [frozenset(code for i, code in columns if row[i] == "1") for row in reader if len(row) == width]


def load_answers(
    raw_dir: Path = RAW_DIR, database_url: str | None = None, entries: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Store the release's answers to the questions that are not yes/no, for every case traced to a release row."""
    if database_url is None:
        app = Settings()
        database_url = app.migration_database_url or app.database_url
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL (or DATABASE_URL) is required")
    entries = [e for e in (load_supplementary() if entries is None else entries) if e.get("kind") == "ddxplus_release"]
    if not entries:
        raise SystemExit("no source release is registered in specs/supplementary_sources.json")
    result: dict[str, Any] = {"releases": {}}
    engine = create_engine(database_url)
    try:
        for entry in entries:
            release_sid = source_id(entry["name"], "*")
            with open_release(raw_dir, entry) as release:
                dictionary = read_dictionary(release)
                wanted = frozenset(code for code, e in dictionary.items() if e["data_type"] != "B")
                possible = {code: {str(v) for v in dictionary[code].get("possible-values") or []} for code in wanted}
                defaults = {code: str(dictionary[code].get("default_value")) for code in wanted}
                keys = {split: release_keys(release, split) for split in SPLITS}
                facts: dict[str, Any] = {"questions": sorted(wanted), "files": {}}
                # Which release row each of our rows is, and which wanted columns of our row hold a 1.
                targets: dict[str, dict[int, tuple[str, str, frozenset[str]]]] = {split: {} for split in SPLITS}
                per_file: dict[str, dict[str, Any]] = {}
                for described in entry["describes"]:
                    name = f"{described['archive']}/{described['file']}"
                    sid = source_id(described["archive"], described["file"])
                    path = raw_dir / described["archive"]
                    if not path.is_file():
                        raise ArchiveError(f"{described['archive']}: missing from {raw_dir}")
                    with zipfile.ZipFile(path) as archive:
                        traced = trace(file_keys(archive, described["file"]), keys)
                        affirmed = _affirmed(archive, described["file"], wanted)
                    with _raw_cursor(engine) as cur:
                        cur.execute("SELECT population -> 'origin' -> 'runs' FROM sources WHERE source_id = %s", (sid,))
                        stored_runs = (cur.fetchone() or [None])[0]
                        cur.execute(
                            "SELECT mapping_id, original_term FROM feature_mappings WHERE source_id = %s", (sid,)
                        )
                        mappings = {
                            m.group(1): mid
                            for mid, term in cur.fetchall()
                            if (m := _CODE.match(term)) and m.group(1) in wanted
                        }
                        cur.execute(
                            """SELECT r.row_number, c.case_id FROM source_records r JOIN dataset_cases c USING (record_id)
                               WHERE r.source_id = %s""",
                            (sid,),
                        )
                        cases = dict(cur.fetchall())
                    info: dict[str, Any] = {
                        "source_id": sid,
                        "rows": traced["rows"],
                        "not_in_release": traced["not_in_release"],
                        "trace_as_stored": stored_runs == traced["runs"],
                        "questions_mapped": len(mappings),
                        "rows_without_a_case": 0,
                        "cells_affirmed": sum(len(found) for found in affirmed),
                        "cells_answered": 0,
                        "rows_where_answers_and_ones_differ": 0,
                        "answers": 0,
                        "answers_not_among_the_possible": 0,
                        "answers_that_are_the_default": 0,
                    }
                    for run in traced["runs"]:
                        for offset in range(run["rows"]):
                            ours = run["our_first_row"] + offset
                            case_id = cases.get(ours)
                            if case_id is None:
                                info["rows_without_a_case"] += 1
                                continue
                            targets[run["release_split"]][run["release_first_row"] + offset] = (
                                name,
                                case_id,
                                affirmed[ours - 1],
                            )
                    per_file[name] = {"info": info, "mappings": mappings}
                    facts["files"][name] = info
                # Nothing is written unless every row is traced exactly as `load-release` stored it: that command
                # registers the release as a source, and a different trace means the files are not the ones it saw.
                facts["ready"] = all(i["trace_as_stored"] and not i["not_in_release"] for i in facts["files"].values())
                if not facts["ready"]:
                    for item in per_file.values():
                        item["info"].update(
                            inserted=0, stored_answers=0, stored_cells=0, stored_cases=0, per_question=[]
                        )
                    result["releases"][entry["name"]] = facts
                    continue
                # One pass over each release split, written straight to the database: the answers are never
                # all held in memory.
                with _raw_cursor(engine) as cur:
                    cur.execute(
                        """CREATE TEMP TABLE tmp_answers (file text, case_id text, mapping_id text, answer text,
                                                          release_split text, release_row integer) ON COMMIT DROP"""
                    )
                    with cur.copy(f"COPY tmp_answers (file, {', '.join(_COLUMNS)}) FROM STDIN") as copy:
                        for split in SPLITS:
                            wanted_rows = targets[split]
                            if not wanted_rows:
                                continue
                            with zipfile.ZipFile(io.BytesIO(release.read(f"release_{split}_patients.zip"))) as inner:
                                member = inner.infolist()[0]
                                if member.file_size > MAX_MEMBER_BYTES:
                                    raise ArchiveError(
                                        f"release {split} patients: {member.file_size} bytes is over the limit"
                                    )
                                with inner.open(member) as raw:
                                    reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
                                    column = next(reader).index("EVIDENCES")
                                    for number, row in enumerate(reader, start=1):
                                        target = wanted_rows.get(number)
                                        if target is None:
                                            continue
                                        name, case_id, ones = target
                                        info, mappings = per_file[name]["info"], per_file[name]["mappings"]
                                        found = sorted(set(answers_in(row[column], wanted)))
                                        answered = frozenset(code for code, _answer in found)
                                        info["cells_answered"] += len(answered)
                                        if answered != ones:
                                            info["rows_where_answers_and_ones_differ"] += 1
                                        for code, answer in found:
                                            info["answers"] += 1
                                            info["answers_not_among_the_possible"] += answer not in possible[code]
                                            info["answers_that_are_the_default"] += answer == defaults[code]
                                            if code in mappings:
                                                copy.write_row((name, case_id, mappings[code], answer, split, number))
                    for name, item in per_file.items():
                        info, ids = item["info"], list(item["mappings"].values())
                        cur.execute(
                            """INSERT INTO case_answers (case_id, mapping_id, answer, source_id, release_split, release_row)
                               SELECT DISTINCT case_id, mapping_id, answer, %s, release_split, release_row
                               FROM tmp_answers WHERE file = %s
                               ON CONFLICT (case_id, mapping_id, answer) DO NOTHING""",
                            (release_sid, name),
                        )
                        info["inserted"] = cur.rowcount
                        # A bulk load leaves the table without statistics, and every later query on it is then planned
                        # badly (measured: a count that takes 3 seconds took more than 5 minutes). Refresh them here.
                        cur.execute("ANALYZE case_answers")
                        cur.execute(
                            """SELECT count(*), count(DISTINCT (case_id, mapping_id)), count(DISTINCT case_id)
                               FROM case_answers WHERE mapping_id = ANY(%s)""",
                            (ids,),
                        )
                        info["stored_answers"], info["stored_cells"], info["stored_cases"] = cur.fetchone()
                        cur.execute(
                            """SELECT m.original_term, count(*), count(DISTINCT a.case_id), count(DISTINCT a.answer)
                               FROM case_answers a JOIN feature_mappings m USING (mapping_id)
                               WHERE a.mapping_id = ANY(%s) GROUP BY 1 ORDER BY 1""",
                            (ids,),
                        )
                        info["per_question"] = [tuple(row) for row in cur.fetchall()]
            result["releases"][entry["name"]] = facts
    finally:
        engine.dispose()
    return result


def check(result: dict[str, Any]) -> list[str]:
    """Everything that would be a gap between our files, the release and what is stored; empty when there is none."""
    diffs: list[str] = []
    for release, facts in result["releases"].items():
        for name, info in facts["files"].items():
            where = f"{name} (from {release})"
            if info["not_in_release"]:
                diffs.append(f"{where}: {info['not_in_release']} rows are not in the release")
            if not info["trace_as_stored"]:
                diffs.append(
                    f"{where}: the rows are traced differently from what load-release stored; run load-release first"
                )
            if not facts.get(
                "ready", True
            ):  # nothing was read or stored for this release: the counts below say nothing
                diffs.append(f"{where}: nothing was read or stored")
                continue
            if info["questions_mapped"] != len(facts["questions"]):
                diffs.append(
                    f"{where}: {info['questions_mapped']} of {len(facts['questions'])} questions have a column mapping"
                )
            if info["rows_without_a_case"]:
                diffs.append(f"{where}: {info['rows_without_a_case']} rows have no loaded case")
            if info["rows_where_answers_and_ones_differ"] or info["cells_affirmed"] != info["cells_answered"]:
                diffs.append(
                    f"{where}: the 1s of our file and the answers of the release differ in "
                    f"{info['rows_where_answers_and_ones_differ']} rows ({info['cells_affirmed']} 1s, {info['cells_answered']} answered)"
                )
            if info["answers_not_among_the_possible"]:
                diffs.append(
                    f"{where}: {info['answers_not_among_the_possible']} answers are not among those the dictionary lists"
                )
            if info["stored_answers"] != info["answers"] or info["stored_cells"] != info["cells_answered"]:
                diffs.append(
                    f"{where}: {info['answers']} answers in {info['cells_answered']} cells read, "
                    f"{info['stored_answers']} in {info['stored_cells']} stored"
                )
    return diffs
