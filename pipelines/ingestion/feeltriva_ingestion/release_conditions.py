"""What the source release says about each of its conditions (M2.13b).

The DDXPlus release describes its 49 conditions in `release_conditions.json`: for each, the
questions it lists as symptoms and as antecedents "characterizing the pathology", a severity
("the lower the more severe", as the publisher's README puts it) and an ICD-10 code.

All of it is stored as what a source says, never as approved knowledge:

- one source record per condition, so every row below points at the entry it came from;
- one `pending` evidence row per condition and listed question, saying the publisher lists the
  question for the condition. It is a list made for simulated patients, not a clinical claim;
- the ICD-10 code as a `pending` vocabulary link, written exactly as the publisher writes it
  (one is lower case and carries a suffix no WHO code has). The edition is not stated, no title
  and no address of the code is held, and the link says so. Codes are internal (decision E63);
- severity and the names, on the release's own source row. Severity is the publisher's label
  for a condition. It is not an urgency rule and is not used as one.

Nothing is written unless `load-release` has registered the release. This module reads one
file of the release and the database.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from feeltriva_api.settings import Settings
from sqlalchemy import create_engine

from .archives import RAW_DIR
from .cases import _raw_cursor
from .load import source_id
from .release import _CODE, load_supplementary, open_release, read_dictionary
from .vocabulary import link_id, store_links

FILE = "release_conditions.json"
EVIDENCE_TYPE = "source_condition_list"
RELATIONSHIPS = {"symptoms": "listed_as_symptom_by_source", "antecedents": "listed_as_antecedent_by_source"}
ICD10, METHOD = "ICD-10", "source_provided"
SEVERITY = "the severity associated with the pathology. The lower the more severe."  # the publisher's README, verbatim


def record_id(release_sid: str, number: int) -> str:
    return "rec_" + hashlib.sha256("\x1f".join((release_sid, FILE, str(number))).encode()).hexdigest()[:24]


def evidence_id(disease_id: str, feature_id: str, relationship: str, release_sid: str) -> str:
    key = "\x1f".join((EVIDENCE_TYPE, release_sid, disease_id, feature_id, relationship))
    return "ev_" + hashlib.sha256(key.encode()).hexdigest()[:24]


def load_conditions(
    raw_dir: Path = RAW_DIR, database_url: str | None = None, entries: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Store what the release lists for each condition as pending, source-provided rows."""
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
                conditions = json.loads(release.read(FILE))
                dictionary = read_dictionary(release)
            described = [source_id(d["archive"], d["file"]) for d in entry["describes"]]
            facts: dict[str, Any] = {
                "conditions": len(conditions),
                "ready": False,
                "without_one_disease": [],
                "codes_without_one_feature": [],
                "listed": {"symptoms": 0, "antecedents": 0},
                "listed_against_the_dictionary": [],
                "expected_evidence": 0,
                "inserted": {"records": 0, "evidence": 0, "links": 0},
                "with_a_code": 0,
                "severity": {},
            }
            result["releases"][entry["name"]] = facts
            with _raw_cursor(engine) as cur:
                cur.execute("SELECT 1 FROM sources WHERE source_id = %s", (release_sid,))
                if cur.fetchone() is None:  # `load-release` registers the release; without it nothing is written
                    continue
                facts["ready"] = True
                # A condition is found through the label the cases of the described files actually carry.
                cur.execute(
                    """SELECT l.original_label, array_agg(DISTINCT l.disease_id)
                       FROM source_records r JOIN dataset_cases c USING (record_id) JOIN case_labels l USING (case_id)
                       WHERE r.source_id = ANY(%s) GROUP BY 1""",
                    (described,),
                )
                diseases = dict(cur.fetchall())
                cur.execute(
                    """SELECT original_term, array_agg(DISTINCT feature_id) FROM feature_mappings
                       WHERE source_id = ANY(%s) GROUP BY 1""",
                    (described,),
                )
                features = {m.group(1): ids for term, ids in cur.fetchall() if (m := _CODE.match(term))}
                items: list[dict[str, Any]] = []
                kept: dict[str, Any] = {}
                wanted: set[str] = set()
                for number, (name, condition) in enumerate(conditions.items(), start=1):
                    ids = diseases.get(name, [])
                    if len(ids) != 1:
                        facts["without_one_disease"].append(name)
                        continue
                    disease_id, rid = ids[0], record_id(release_sid, number)
                    content = json.dumps(condition, sort_keys=True, ensure_ascii=False)
                    cur.execute(
                        """INSERT INTO source_records (record_id, source_id, file_path, row_number, content_hash,
                                                       raw_object_uri, quality_flags)
                           VALUES (%s, %s, %s, %s, %s, %s, '[]'::jsonb) ON CONFLICT DO NOTHING""",
                        (
                            rid,
                            release_sid,
                            FILE,
                            number,
                            hashlib.sha256(content.encode()).hexdigest(),
                            f"zip://{entry['name']}#{FILE}",
                        ),
                    )
                    facts["inserted"]["records"] += cur.rowcount
                    for group, relationship in RELATIONSHIPS.items():
                        said = group[:-1]  # "symptom" or "antecedent"
                        for code in condition.get(group) or {}:
                            facts["listed"][group] += 1
                            found = features.get(code, [])
                            if len(found) != 1 or code not in dictionary:
                                facts["codes_without_one_feature"].append(f"{name}: {code}")
                                continue
                            by_dictionary = "antecedent" if dictionary[code]["is_antecedent"] else "symptom"
                            if by_dictionary != said:
                                facts["listed_against_the_dictionary"].append(f"{name}: {code} listed as {said}")
                            eid = evidence_id(disease_id, found[0], relationship, release_sid)
                            wanted.add(eid)
                            context = {
                                "source_id": release_sid,
                                "file": FILE,
                                "condition": name,
                                "question_code": code,
                                "question": dictionary[code].get("question_en", ""),
                                "listed_as": said,
                                "dictionary_says": by_dictionary,
                                "basis": f"the publisher lists this question among the {group} characterizing the condition; "
                                "its patients are simulated, and a list is not a clinical claim",
                            }
                            cur.execute(
                                """INSERT INTO disease_feature_evidence (evidence_id, disease_id, feature_id, record_id,
                                                                         relationship, context, evidence_type, status)
                                   VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, 'pending') ON CONFLICT (evidence_id) DO NOTHING""",
                                (
                                    eid,
                                    disease_id,
                                    found[0],
                                    rid,
                                    relationship,
                                    json.dumps(context, sort_keys=True),
                                    EVIDENCE_TYPE,
                                ),
                            )
                            facts["inserted"]["evidence"] += cur.rowcount
                    code_as_written = str(condition.get("icd10-id") or "")
                    severity = condition.get("severity")
                    facts["severity"][str(severity)] = facts["severity"].get(str(severity), 0) + 1
                    link = {
                        "system": ICD10,
                        "version": "as written in the source release; edition not stated",
                        "code": code_as_written,
                        "title": str(condition.get("cond-name-eng") or name),
                        "uri": None,
                        "method": METHOD,
                        "detail": {
                            "source_id": release_sid,
                            "record_id": rid,
                            "title_is": "the publisher's name of the condition; no ICD-10 title or address of the code is held",
                        },
                    }
                    facts["with_a_code"] += bool(code_as_written)
                    items.append(
                        {"type": "disease", "id": disease_id, "name": name, "links": [link] if code_as_written else []}
                    )
                    kept[name] = {
                        "disease_id": disease_id,
                        "record_id": rid,
                        "name_en": condition.get("cond-name-eng"),
                        "name_fr": condition.get("cond-name-fr"),
                        "icd10_as_written": code_as_written,
                        "severity": severity,
                        "symptoms": len(condition.get("symptoms") or {}),
                        "antecedents": len(condition.get("antecedents") or {}),
                    }
                facts["expected_evidence"] = len(wanted)
                facts["inserted"]["links"] = store_links(cur, items).get(ICD10, 0)
                cur.execute(
                    """UPDATE sources SET population = coalesce(population, '{}'::jsonb) || %s::jsonb
                       WHERE source_id = %s AND coalesce(population, '{}'::jsonb) -> 'conditions' IS DISTINCT FROM %s::jsonb""",
                    (
                        json.dumps({"conditions": kept, "severity_as_documented": SEVERITY}, sort_keys=True),
                        release_sid,
                        json.dumps(kept, sort_keys=True),
                    ),
                )
                cur.execute(
                    """SELECT count(*), count(*) FILTER (WHERE status = 'pending'), count(DISTINCT disease_id),
                              count(DISTINCT feature_id), count(*) FILTER (WHERE record_id IS NULL)
                       FROM disease_feature_evidence WHERE evidence_type = %s AND context ->> 'source_id' = %s""",
                    (EVIDENCE_TYPE, release_sid),
                )
                keys = ("rows", "pending", "diseases", "features", "without_a_record")
                facts["stored_evidence"] = dict(zip(keys, cur.fetchone(), strict=True))
                # A link is one disease, one vocabulary and one code. If another source has already said the same,
                # the link is there and nothing new is stored: what is checked is that every link exists.
                expected = [
                    link_id(item["id"], link["system"], link["version"], link["code"])
                    for item in items
                    for link in item["links"]
                ]
                cur.execute(
                    """SELECT count(*), count(*) FILTER (WHERE status = 'pending'),
                              count(*) FILTER (WHERE status <> 'pending' AND reviewer IS NULL)
                       FROM terminology_links WHERE link_id = ANY(%s)""",
                    (expected,),
                )
                facts["stored_links"] = dict(
                    zip(("rows", "pending", "decided_without_reviewer"), cur.fetchone(), strict=True)
                )
                cur.execute(
                    "SELECT count(*) FROM source_records WHERE source_id = %s AND file_path = %s", (release_sid, FILE)
                )
                facts["stored_records"] = cur.fetchone()[0]
    finally:
        engine.dispose()
    return result


def check(result: dict[str, Any]) -> list[str]:
    """Everything that would be a gap between the release's file and what is stored; empty when there is none."""
    diffs: list[str] = []
    for release, facts in result["releases"].items():
        if not facts["ready"]:
            diffs.append(
                f"{release}: the release is not registered as a source; run load-release first. Nothing was written"
            )
            continue
        for name in facts["without_one_disease"]:
            diffs.append(f"{release}: the condition {name!r} is not the label of exactly one disease candidate")
        for item in facts["codes_without_one_feature"]:
            diffs.append(f"{release}: {item} is not the question of exactly one feature")
        mapped = facts["conditions"] - len(facts["without_one_disease"])
        if facts["stored_records"] != mapped:
            diffs.append(f"{release}: {mapped} conditions read, {facts['stored_records']} source records stored")
        stored = facts["stored_evidence"]
        if stored["rows"] != facts["expected_evidence"] or stored["without_a_record"]:
            diffs.append(
                f"{release}: {facts['expected_evidence']} listed questions read, {stored['rows']} evidence rows stored "
                f"({stored['without_a_record']} without a source record)"
            )
        links = facts["stored_links"]
        if links["rows"] != facts["with_a_code"] or links["decided_without_reviewer"]:
            diffs.append(
                f"{release}: {facts['with_a_code']} conditions carry a code, {links['rows']} links stored "
                f"({links['decided_without_reviewer']} decided without a reviewer)"
            )
    return diffs
