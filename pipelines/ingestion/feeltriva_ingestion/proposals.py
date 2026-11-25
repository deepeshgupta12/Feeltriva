"""Names without a link, and the terms a reviewer could confirm for them, stored for review (M2.4b).

The look-ups store a link only for an exact name (M2.11, M2.14) or for the one identifier a
vocabulary marks equivalent (M2.16). What they could not link was written to review files only,
where no screen could show it and no decision could be recorded. Each look-up now also stores
those results as rows of `link_proposals`:

- `link-vocabularies`: the best ICD-11 search result of a name that no entity carries exactly, when
  its score is 0.9 or more (the "close results" of M2.11);
- `link-ontologies`: for each name and each of HPO and MONDO, the reason it has no link, with one
  row per near term; a name with no near term, and a question sentence, get one row without a term;
- `import-identifiers`: for a label whose MONDO term lists several identifiers of SNOMED CT or of
  ICD-11 as equivalent, one row per identifier.

A row is a proposal and never a link (decision E56): the link is made only when a reviewer confirms
the row, by the review service. A row keeps the code, the title and the address of its term
together, as the WHO terms require wherever ICD-11 is stored.

A later run adds what is new and leaves every stored row as it is. A full run also removes the rows
of its own kinds that the look-up no longer gives, but never one a reviewer has decided or written
a note on.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Why a row is there. The first seven name a term a reviewer may confirm (for a plain word these are the nearest
# terms; the abbreviation is ruled out). A row of the others records only why a name has no link: the term of a
# `term_not_linkable` row is shown and cannot be confirmed. Which kinds can be confirmed is the review service's
# rule (`feeltriva_api.review_proposals.CONFIRMABLE`).
CLOSE_RESULT = "close_search_result"
ABBREVIATION = "abbreviation_only"
SEVERAL_TERMS = "several_terms_carry_the_name"
SEVERAL_EQUIVALENT = "several_identifiers_marked_equivalent"
LOOSER = "looser_synonym"
NEAREST = "nearest_by_shared_words"
PLAIN_WORD = "plain_word_not_the_abbreviation"
NOT_LINKABLE = "term_not_linkable"
NO_TERM = "no_term_near"
SENTENCE = "question_sentence_not_looked_up"
TARGET = "link_proposal"  # the review target type the service records notes and decisions under


def proposal_id(subject: str, system: str, version: str, basis: str, code: str) -> str:
    key = "\x1f".join((subject, system, version, basis, code))
    return "lp_" + hashlib.sha256(key.encode()).hexdigest()[:24]


def row(
    item: dict[str, Any],
    system: str,
    version: str,
    basis: str,
    reason: str,
    term: dict[str, str] | None,
    link: str | None,
    **detail: Any,
) -> dict[str, Any]:
    """One proposal for one of our names. `term` holds code, title and uri, or is None when no term is
    proposed; `link` is the ID the link will have once a reviewer confirms the term."""
    if (term is None) != (link is None):
        raise ValueError("a proposal names a term and the link it would make, or neither")
    if term is not None and not (term["code"] and term["title"] and term["uri"]):
        raise ValueError(f"{item['name']}: {system}: a proposed term needs its code, title and address together")
    return {
        "proposal_id": proposal_id(item["id"], system, version, basis, term["code"] if term else ""),
        "disease_id": item["id"] if item["type"] == "disease" else None,
        "feature_id": item["id"] if item["type"] == "feature" else None,
        "system": system,
        "version": version,
        "basis": basis,
        "reason": reason,
        "code": term["code"] if term else None,
        "title": term["title"] if term else None,
        "uri": term["uri"] if term else None,
        "link_id": link,
        "detail": {key: value for key, value in detail.items() if value not in ("", None)},
    }


def store(cur: Any, rows: list[dict[str, Any]], *, bases: tuple[str, ...], complete: bool) -> dict[str, Any]:
    """Insert the proposals; a row already stored keeps everything, its review decision included.

    bases: the kinds of proposal the calling look-up gives. complete: the look-up covered every name
    (not only those of some sources), so a stored row of these kinds that it no longer gives is out of
    date and is removed, unless a reviewer has decided it or written a note on it."""
    unique = {entry["proposal_id"]: entry for entry in rows}
    inserted = 0
    for entry in unique.values():
        cur.execute(
            """INSERT INTO link_proposals (proposal_id, disease_id, feature_id, system, system_version, basis, reason,
                                           code, title, uri, link_id, detail)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb) ON CONFLICT (proposal_id) DO NOTHING""",
            (
                entry["proposal_id"],
                entry["disease_id"],
                entry["feature_id"],
                entry["system"],
                entry["version"],
                entry["basis"],
                entry["reason"],
                entry["code"],
                entry["title"],
                entry["uri"],
                entry["link_id"],
                json.dumps(entry["detail"], sort_keys=True),
            ),
        )
        inserted += cur.rowcount
    ids, kinds = list(unique), list(bases)
    removed = 0
    if complete:
        cur.execute(
            """DELETE FROM link_proposals p
               WHERE p.basis = ANY(%s) AND NOT (p.proposal_id = ANY(%s)) AND p.status = 'pending' AND p.reviewer IS NULL
                 AND NOT EXISTS (SELECT 1 FROM review_notes n
                                 WHERE n.target_type = %s AND n.target_id = p.proposal_id)""",
            (kinds, ids, TARGET),
        )
        removed = cur.rowcount
    cur.execute("SELECT count(*) FROM link_proposals WHERE proposal_id = ANY(%s)", (ids,))
    present = cur.fetchone()[0]
    cur.execute(
        """SELECT count(*) FILTER (WHERE NOT (proposal_id = ANY(%s))),
                  count(*) FILTER (WHERE status <> 'pending' AND reviewer IS NULL)
           FROM link_proposals WHERE basis = ANY(%s)""",
        (ids, kinds),
    )
    kept, unsigned = cur.fetchone()
    cur.execute(
        """SELECT basis, system, status::text, count(*), count(*) FILTER (WHERE code IS NOT NULL),
                  count(DISTINCT coalesce(disease_id, feature_id))
           FROM link_proposals WHERE basis = ANY(%s) GROUP BY 1, 2, 3 ORDER BY 1, 2, 3""",
        (kinds,),
    )
    return {
        "given": len(unique),
        "given_twice": len(rows) - len(unique),
        "inserted": inserted,
        "removed_out_of_date": removed,
        "missing": len(unique) - present,
        # Rows of these kinds the look-up did not give this time: decided or noted rows of an earlier full run,
        # or simply the rest of the table when only some sources were looked at.
        "kept_not_given": kept if complete else None,
        "decided_without_reviewer": unsigned,
        "table": [tuple(found) for found in cur.fetchall()],
    }


def check(stored: dict[str, Any]) -> list[str]:
    """What would be a gap in the stored proposals; empty when there is none."""
    diffs = []
    if stored["given_twice"]:
        diffs.append(f"{stored['given_twice']} proposals were given twice for one name, vocabulary and term")
    if stored["missing"]:
        diffs.append(f"{stored['missing']} proposals of this run are not in the table")
    if stored["decided_without_reviewer"]:
        diffs.append(
            f"{stored['decided_without_reviewer']} proposals were decided without a recorded reviewer; only a "
            "reviewer may decide one"
        )
    return diffs


def lines(stored: dict[str, Any]) -> list[str]:
    """The stored proposals in words, for the command's report."""
    out = [
        f"For review (no link is made before a reviewer confirms): {stored['given']} rows given, "
        f"{stored['inserted']} new, {stored['removed_out_of_date']} out of date and removed"
        + (f", {stored['kept_not_given']} kept from an earlier run" if stored["kept_not_given"] else "")
    ]
    for basis, system, status, rows, with_term, names in stored["table"]:
        out.append(
            f"  {basis.replace('_', ' ')}: {system}: {status}: {rows} rows for {names} names, {with_term} naming a term"
        )
    return out
