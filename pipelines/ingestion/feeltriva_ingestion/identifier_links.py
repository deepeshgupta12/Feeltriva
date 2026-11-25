"""Candidate SNOMED CT and ICD-11 links for our labels, taken from the MONDO terms they are linked to (M2.16).

For every label that has a MONDO link which no reviewer has rejected, the identifiers MONDO
lists for that term are graded (`mondo_identifiers.py`) and those MONDO marks equivalent are
stored as candidate links with review status `pending`. Each such link names the MONDO term and
the marks it came through, so that it can be traced and, if the MONDO link is later rejected,
found again.

Deduplication, as the owner set it (E62): one row per label and code. When the ICD-11 code that
MONDO leads to is the one the name search of M2.11 already stored for the label, no second row
is made; the existing row is noted as also reached through MONDO. The name kept with a code is
the official name of the code's own vocabulary: WHO's title for ICD-11. For SNOMED CT no name is
held, and the link says that its title is MONDO's name of the equivalent disease.

No gaps: every label with a MONDO link has one recorded outcome for SNOMED CT and one for
ICD-11; `check` fails the command otherwise. The list this command writes relates MONDO, SNOMED
CT and ICD-11 identifiers; it stays in the private database and in a file outside Git, and no
code is shown to a user (E63).
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from feeltriva_api.settings import Settings
from sqlalchemy import create_engine

from . import proposals
from .archives import RAW_DIR
from .cases import _raw_cursor
from .mondo_identifiers import (
    ICD_FOUNDATION,
    LINKED,
    LINKED_FOUNDATION,
    SEVERAL,
    SNOMED,
    SNOMED_URI,
    UNKNOWN_TO_WHO,
    Identifier,
    grade,
    read_identifiers,
    resolve_icd,
)
from .ontologies import MONDO
from .release import load_supplementary
from .vocabulary import ICD, REVIEW_DIR, IcdClient, IcdSettings, link_id, store_links

REVIEW_FILE = "mondo_identifiers.csv"
METHOD = "mondo_equivalent"
ICD11 = "ICD-11"  # the outcome of a label for ICD-11, whichever of the two kinds of link it leads to
SAME, DIFFERENT = "the name search found the same code", "the name search found a different code"
SAME_CATEGORY = "the name search stored only the unspecified or other-specified sub-code of this same category"
_RESIDUAL = ("unspecified", "other")  # how WHO ends the address of a residual sub-code of a category


def _agreement(mms: dict[str, Any], known: dict[str, tuple[str, str]]) -> tuple[str, list[str]]:
    """How the code MONDO leads to compares with what the name search of M2.11 stored for the label, and the
    link ids of the name-search rows to note it on.

    The name search codes a bare category name the way a coder would, as its "unspecified" sub-code; MONDO
    leads to the category itself. That is the same category at two grains, not a disagreement."""
    if mms["code"] in known:
        return SAME, [known[mms["code"]][1]]
    residuals = [
        row_id
        for uri, row_id in known.values()
        if uri.rsplit("/", 1)[0] == mms["uri"] and uri.rsplit("/", 1)[-1] in _RESIDUAL
    ]
    if residuals:
        return SAME_CATEGORY, residuals
    return (DIFFERENT if known else ""), []


def _detail(item: dict[str, Any], chosen: Identifier, **more: Any) -> dict[str, Any]:
    return {"via": {"vocabulary": MONDO, **item["mondo"]}, "marks": list(chosen.marks), **more}


def import_identifiers(
    raw_dir: Path = RAW_DIR,
    database_url: str | None = None,
    client: IcdClient | None = None,
    entries: list[dict[str, Any]] | None = None,
    source_ids: list[str] | None = None,
    progress: Callable[[str], None] = lambda _message: None,
) -> dict[str, Any]:
    """Store, as pending links, the SNOMED CT and ICD-11 identifiers MONDO marks equivalent to the terms our labels link to.

    source_ids limits the labels to those mapped from these sources (used by tests); default all."""
    entry = next(
        (e for e in (load_supplementary() if entries is None else entries) if e.get("kind") == "mondo_release"), None
    )
    if entry is None:
        raise SystemExit("no MONDO file is registered in specs/supplementary_sources.json")
    if database_url is None:
        app = Settings()
        database_url = app.migration_database_url or app.database_url
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL (or DATABASE_URL) is required")
    progress(f"reading {entry['name']}")
    version, identifiers, counted = read_identifiers(raw_dir, entry)
    scope = (
        """AND (t.disease_id IN (SELECT disease_id FROM disease_mappings WHERE source_id = ANY(%s))
                OR t.feature_id IN (SELECT feature_id FROM feature_mappings WHERE source_id = ANY(%s)))"""
        if source_ids is not None
        else ""
    )
    params: tuple[Any, ...] = (MONDO, version, *((source_ids, source_ids) if source_ids is not None else ()))
    engine = create_engine(database_url)
    items: list[dict[str, Any]] = []
    release = ""
    try:
        with _raw_cursor(engine) as cur:  # a short read: the lookups below hold no database transaction open
            cur.execute(
                f"""SELECT coalesce(t.disease_id, t.feature_id), t.disease_id IS NOT NULL,
                           coalesce(d.preferred_name, f.preferred_name), t.code, t.title, t.match_method, t.link_id,
                           t.status::text
                    FROM terminology_links t LEFT JOIN diseases d USING (disease_id) LEFT JOIN features f USING (feature_id)
                    WHERE t.system = %s AND t.system_version = %s {scope} ORDER BY 1, t.code""",  # noqa: S608 - fixed text
                params,
            )
            rows = cur.fetchall()
            cur.execute(
                """SELECT coalesce(disease_id, feature_id), code, coalesce(uri, ''), link_id FROM terminology_links
                   WHERE system = %s AND match_method <> %s AND status <> 'rejected'""",
                (ICD, METHOD),
            )
            by_name: dict[str, dict[str, tuple[str, str]]] = {}  # label -> ICD-11 code -> (address, link id)
            for subject_id, code, uri, row_id in cur.fetchall():
                by_name.setdefault(subject_id, {})[code] = (uri, row_id)
        usable = [row for row in rows if row[7] != "rejected"]
        progress(f"{len(usable)} labels with a MONDO link")
        for number, (subject_id, is_disease, name, code, title, our_match, mondo_link, _status) in enumerate(usable, 1):
            if number % 100 == 0:
                progress(f"{number} of {len(usable)} done" + (f", {client.calls} new WHO calls" if client else ""))
            item: dict[str, Any] = {
                "type": "disease" if is_disease else "feature",
                "id": subject_id,
                "name": name,
                "mondo": {
                    "code": code,
                    "title": title,
                    "release": version,
                    "our_match": our_match,
                    "link_id": mondo_link,
                },
                "links": [],
                "outcomes": {},
                "agreement": "",
                "note_on": [],
            }
            listed = identifiers.get(code, ())
            outcome, chosen, of = grade(listed, SNOMED)
            item["outcomes"][SNOMED] = {"outcome": outcome, "identifiers": of, "stored": None}
            if chosen is not None:
                link = {
                    "system": SNOMED,
                    "version": f"as listed in MONDO {version}",
                    "code": chosen.number,
                    "title": title,
                    "uri": SNOMED_URI + chosen.number,
                    "method": METHOD,
                    "detail": _detail(
                        item,
                        chosen,
                        title_is="MONDO's name of the equivalent disease; the SNOMED CT release, and so its own name, is not held",
                    ),
                }
                item["links"].append(link)
                item["outcomes"][SNOMED]["stored"] = link
            outcome, chosen, of = grade(listed, ICD_FOUNDATION)
            record: dict[str, Any] = {"outcome": outcome, "identifiers": of, "stored": None, "who": None}
            if outcome == SEVERAL:  # none is chosen; each goes before a reviewer under WHO's own title (M2.4b)
                client = client or IcdClient(IcdSettings())
                release = release or client.release()
                record["who_of_each"] = {
                    found.number: resolve_icd(client, release, found.number) for found in of if found.equivalent
                }
            if chosen is not None:
                client = client or IcdClient(IcdSettings())
                release = release or client.release()
                who = resolve_icd(client, release, chosen.number)
                record["who"] = who
                if who is None:
                    record["outcome"] = UNKNOWN_TO_WHO
                elif who["mms"] and who["mms"]["same_entity"]:
                    record["stored"] = {
                        "system": ICD,
                        "version": release,
                        "code": who["mms"]["code"],
                        "title": who["mms"]["title"],
                        "uri": who["mms"]["uri"],
                        "method": METHOD,
                        "detail": _detail(item, chosen, foundation_uri=who["uri"], residual=False),
                    }
                    item["agreement"], item["note_on"] = _agreement(who["mms"], by_name.get(subject_id, {}))
                else:
                    record["outcome"] = LINKED_FOUNDATION
                    record["stored"] = {
                        "system": ICD_FOUNDATION,
                        "version": release,
                        "code": chosen.number,
                        "title": who["title"],
                        "uri": who["uri"],
                        "method": METHOD,
                        "detail": _detail(item, chosen, coded_in_mms_under=who["mms"]),
                    }
                if record["stored"] is not None:
                    item["links"].append(record["stored"])
            item["outcomes"][ICD11] = record
            items.append(item)
        with _raw_cursor(engine) as cur:
            inserted = store_links(cur, items)
            proposed = proposals.store(
                cur,
                several_identifiers(items, version, release),
                bases=(proposals.SEVERAL_EQUIVALENT,),
                complete=source_ids is None,
            )
            # One row per label and code: a code the name search already stored is noted, not repeated. Where the
            # name search stored the unspecified sub-code, that row is noted with the category MONDO leads to.
            for item in items:
                link = item["outcomes"][ICD11]["stored"]
                if not item["note_on"] or link is None:
                    continue
                key = "also_through_mondo" if item["agreement"] == SAME else "category_through_mondo"
                noted = {
                    "icd_code": link["code"],
                    "icd_title": link["title"],
                    "foundation_uri": link["detail"][
                        "foundation_uri"
                    ],  # the entity MONDO names, kept beside its MMS code
                    "via": link["detail"]["via"],
                }
                for row_id in item["note_on"]:
                    cur.execute(
                        """UPDATE terminology_links SET detail = detail || jsonb_build_object(%s::text, %s::jsonb)
                           WHERE link_id = %s AND match_method <> %s AND (detail -> %s) IS DISTINCT FROM %s::jsonb""",
                        (
                            key,
                            json.dumps(noted, sort_keys=True),
                            row_id,
                            METHOD,
                            key,
                            json.dumps(noted, sort_keys=True),
                        ),
                    )
            cur.execute(
                """SELECT system, status::text, count(*),
                          count(*) FILTER (WHERE uri IS NULL OR uri = '' OR title = '' OR code = ''),
                          count(*) FILTER (WHERE status <> 'pending' AND reviewer IS NULL)
                   FROM terminology_links WHERE match_method = %s GROUP BY 1, 2 ORDER BY 1, 2""",
                (METHOD,),
            )
            stored = [tuple(row) for row in cur.fetchall()]
            cur.execute(
                """SELECT count(*) FROM terminology_links t JOIN terminology_links m ON m.link_id = t.detail -> 'via' ->> 'link_id'
                   WHERE t.match_method = %s AND t.status = 'pending' AND m.status = 'rejected'""",
                (METHOD,),
            )
            on_rejected = cur.fetchone()[0]
            cur.execute(
                """WITH n AS (SELECT disease_id, count(*) AS labels FROM case_labels GROUP BY 1),
                        l AS (SELECT disease_id, bool_or(system = %s) AS snomed, bool_or(system = ANY(%s)) AS icd
                              FROM terminology_links WHERE disease_id IS NOT NULL AND status <> 'rejected' GROUP BY 1)
                   SELECT coalesce(sum(n.labels), 0), coalesce(sum(n.labels) FILTER (WHERE l.snomed), 0),
                          coalesce(sum(n.labels) FILTER (WHERE l.icd), 0),
                          coalesce(sum(n.labels) FILTER (WHERE l.disease_id IS NOT NULL), 0)
                   FROM n LEFT JOIN l USING (disease_id)""",
                (SNOMED, [ICD, ICD_FOUNDATION]),
            )
            total, with_snomed, with_icd, with_any = cur.fetchone()
    finally:
        engine.dispose()
    return {
        "mondo_release": version,
        "icd_release": release,
        "counted": counted,
        "items": items,
        "mondo_links": {"read": len(rows), "rejected_and_not_used": len(rows) - len(usable)},
        "inserted": {system: inserted.get(system, 0) for system in (SNOMED, ICD, ICD_FOUNDATION)},
        "stored": stored,
        "resting_on_a_rejected_mondo_link": on_rejected,
        "who_calls": client.calls if client else 0,
        "case_labels": {
            "all": int(total),
            "label_has_snomed_ct": int(with_snomed),
            "label_has_icd_11": int(with_icd),
            "label_has_any_link": int(with_any),
        },
        "proposals": proposed,
        "for_review": proposals.lines(proposed),
    }


def summarise(result: dict[str, Any]) -> dict[str, Any]:
    rows: Counter[tuple[str, str, str]] = Counter()
    agreement: Counter[str] = Counter()
    groups: Counter[str] = Counter()
    for item in result["items"]:
        group = "disease labels" if item["type"] == "disease" else "feature terms"
        groups[group] += 1
        for vocabulary, record in item["outcomes"].items():
            rows[(group, vocabulary, record["outcome"].replace("_", " "))] += 1
        if item["agreement"]:
            agreement[item["agreement"]] += 1
    return {"rows": rows, "agreement": agreement, "groups": groups}


def check(result: dict[str, Any]) -> list[str]:
    """Everything that would be a gap or a link MONDO does not mark equivalent; empty when there is none."""
    diffs: list[str] = []
    for item in result["items"]:
        if set(item["outcomes"]) != {SNOMED, ICD11}:
            diffs.append(f"{item['name']}: an outcome is missing")
            continue
        for vocabulary, record in item["outcomes"].items():
            link, linked = record["stored"], record["outcome"] in (LINKED, LINKED_FOUNDATION)
            if (link is None) == linked:
                diffs.append(f"{item['name']}: {vocabulary}: outcome and link disagree")
            if link is not None:
                equivalent = [found for found in record["identifiers"] if found.equivalent]
                if len(equivalent) != 1 or not (link["code"] and link["title"] and link["uri"]):
                    diffs.append(
                        f"{item['name']}: {vocabulary}: a link without one equivalent identifier, code, title and address"
                    )
                if (
                    link["detail"]["via"]["code"] != item["mondo"]["code"]
                    or "MONDO:equivalentTo" not in link["detail"]["marks"]
                ):
                    diffs.append(f"{item['name']}: {vocabulary}: a link that does not name its MONDO term and mark")
        if len(item["links"]) != sum(1 for record in item["outcomes"].values() if record["stored"] is not None):
            diffs.append(f"{item['name']}: links and outcomes differ in number")
    for system, status, _count, incomplete, unsigned in result["stored"]:
        if incomplete:
            diffs.append(f"{incomplete} stored {system} links ({status}) lack a code, a title or an address")
        if unsigned:
            diffs.append(f"{unsigned} stored {system} links are {status} without a recorded reviewer")
    if result["resting_on_a_rejected_mondo_link"]:
        diffs.append(
            f"{result['resting_on_a_rejected_mondo_link']} pending links rest on a MONDO link a reviewer has rejected"
        )
    return diffs + proposals.check(result["proposals"])


def write_review(result: dict[str, Any], out_dir: Path = REVIEW_DIR) -> Path:
    """One row per label, vocabulary and identifier MONDO lists (or one row saying there is none). Kept outside Git."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / REVIEW_FILE
    head = ["type", "id", "name", "mondo_code", "mondo_title", "how_our_label_matched_mondo", "vocabulary", "outcome"]
    tail = [
        "identifier",
        "marks",
        "stored_as",
        "stored_code",
        "official_title",
        "uri",
        "broader_mms_code",
        "broader_mms_title",
        "agreement",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(head + tail)
        for item in result["items"]:
            mondo = item["mondo"]
            for vocabulary, record in item["outcomes"].items():
                start = [
                    item["type"],
                    item["id"],
                    item["name"],
                    mondo["code"],
                    mondo["title"],
                    mondo["our_match"],
                    vocabulary,
                ]
                link = record["stored"]
                broader = ((link or {}).get("detail", {}).get("coded_in_mms_under")) or {}
                for found in record["identifiers"] or (None,):
                    chosen = link is not None and found is not None and found.equivalent
                    writer.writerow(
                        [
                            *start,
                            record["outcome"],
                            found.number if found else "",
                            ", ".join(found.marks) if found else "",
                            link["system"] if chosen else "",
                            link["code"] if chosen else "",
                            ("" if link["system"] == SNOMED else link["title"]) if chosen else "",
                            link["uri"] if chosen else "",
                            broader.get("code", "") if chosen else "",
                            broader.get("title", "") if chosen else "",
                            item["agreement"] if chosen and vocabulary == ICD11 else "",
                        ]
                    )
    return path


# -- several identifiers marked equivalent, for a reviewer (M2.4b) ------------------------------------
_SEVERAL_REASON = "MONDO marks {n} {vocabulary} identifiers as equivalent to this term; a person chooses"


def several_identifiers(items: list[dict[str, Any]], mondo_version: str, icd_release: str) -> list[dict[str, Any]]:
    """One proposal per identifier, for each label whose MONDO term lists several of one vocabulary as equivalent.

    An ICD-11 identifier is kept in the same form as the single equivalent one is (decision E62): its MMS
    code when WHO codes the entity as itself, otherwise the foundation entity with the broader MMS code noted
    beside it. An identifier WHO has no entity for gets a row without a term."""
    rows = []
    for item in items:
        via = {"vocabulary": MONDO, **item["mondo"]}
        record = item["outcomes"][SNOMED]
        if record["outcome"] == SEVERAL:
            equivalent = [found for found in record["identifiers"] if found.equivalent]
            listed = f"as listed in MONDO {mondo_version}"
            for found in equivalent:
                rows.append(
                    proposals.row(
                        item,
                        SNOMED,
                        listed,
                        proposals.SEVERAL_EQUIVALENT,
                        _SEVERAL_REASON.format(n=len(equivalent), vocabulary=SNOMED),
                        {"code": found.number, "title": item["mondo"]["title"], "uri": SNOMED_URI + found.number},
                        link_id(item["id"], SNOMED, listed, found.number),
                        via=via,
                        marks=list(found.marks),
                        title_is="MONDO's name of the equivalent disease; the SNOMED CT release, and so its own name, "
                        "is not held",
                    )
                )
        record = item["outcomes"][ICD11]
        if record["outcome"] == SEVERAL:
            equivalent = [found for found in record["identifiers"] if found.equivalent]
            reason = _SEVERAL_REASON.format(n=len(equivalent), vocabulary=ICD11)
            for found in equivalent:
                who = record["who_of_each"].get(found.number)
                if who is None:
                    rows.append(
                        proposals.row(
                            item,
                            ICD_FOUNDATION,
                            icd_release,
                            proposals.SEVERAL_EQUIVALENT,
                            f"{reason}; WHO has no entity with the identifier {found.number}",
                            None,
                            None,
                            via=via,
                            marks=list(found.marks),
                            identifier=found.number,
                        )
                    )
                    continue
                coded = who["mms"]
                if coded and coded["same_entity"]:
                    system, term = ICD, {"code": coded["code"], "title": coded["title"], "uri": coded["uri"]}
                    more: dict[str, Any] = {"foundation_uri": who["uri"], "residual": False}
                else:
                    system, term = ICD_FOUNDATION, {"code": found.number, "title": who["title"], "uri": who["uri"]}
                    more = {"coded_in_mms_under": coded}
                rows.append(
                    proposals.row(
                        item,
                        system,
                        icd_release,
                        proposals.SEVERAL_EQUIVALENT,
                        reason,
                        term,
                        link_id(item["id"], system, icd_release, term["code"]),
                        via=via,
                        marks=list(found.marks),
                        **more,
                    )
                )
    return rows
