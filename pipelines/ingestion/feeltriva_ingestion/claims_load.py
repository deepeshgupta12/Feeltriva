"""Putting the single claims of every stored statement into the review queue (M2.6).

`extract_claims` applies the rules of `claims.py` to each stored statement and stores the
claims with review status `pending`. A claim keeps its statement, so its source record and URL
are those of the statement (`statement_sources`). A claim that is already stored keeps its row
and any review decision.

For a list item of a symptom statement whose plain name is exactly the name of one feature,
that feature is proposed on the claim. A name that fits several features is proposed for none.
This is the "atomic feature relation" of the handoff: an item of the statement's own list, kept
in the review queue, not written to the evidence table before a reviewer has seen it.

No gaps: every statement must have its sentences stored, the sentences must hold all of its
text, and every stored claim must be exactly its statement's text at its offsets. `check` fails
the command otherwise.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any

from feeltriva_api.settings import Settings
from sqlalchemy import create_engine

from .cases import _raw_cursor
from .claims import LIST_ITEM, SENTENCE, VERSION, item_name, split
from .meanings import is_question
from .vocabulary import query_for

_SPACE = re.compile(r"\s+")


def claim_id(statement_id: str, kind: str, start: int, end: int) -> str:
    return "cl_" + hashlib.sha256("\x1f".join((statement_id, kind, str(start), str(end))).encode()).hexdigest()[:24]


def feature_names(cur: Any) -> dict[str, list[str]]:
    """Plain name -> the features carrying it, for features that are names and not question sentences."""
    cur.execute(
        """SELECT f.feature_id, f.preferred_name, max(m.original_term)
           FROM features f JOIN feature_mappings m USING (feature_id) GROUP BY 1, 2"""
    )
    names: dict[str, list[str]] = {}
    for feature_id, name, heading in cur.fetchall():
        if not is_question(heading):
            names.setdefault(query_for(name), []).append(feature_id)
    return names


def extract_claims(database_url: str | None = None, statement_ids: list[str] | None = None) -> dict[str, Any]:
    """Store the claims of every statement (or of the given ones: used by tests) as pending rows."""
    if database_url is None:
        app = Settings()
        database_url = app.migration_database_url or app.database_url
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL (or DATABASE_URL) is required")
    scope = "WHERE statement_id = ANY(%s)" if statement_ids is not None else ""
    params: tuple[Any, ...] = (statement_ids,) if statement_ids is not None else ()
    result: dict[str, Any] = {
        "version": VERSION,
        "statements": Counter(),
        "claims": Counter(),
        "split_sentences": Counter(),
        "not_split": Counter(),
        "cues": Counter(),
        "features": Counter(),
        "not_covered": [],
        "inserted": 0,
    }
    engine = create_engine(database_url)
    try:
        with _raw_cursor(engine) as cur:
            names = feature_names(cur)
            cur.execute(f"SELECT statement_id, statement_type, text_content FROM statements {scope} ORDER BY 1", params)  # noqa: S608 - fixed text
            statements = cur.fetchall()
            rows = []
            for statement_id, kind, body in statements:
                claims, reasons = split(body)
                result["statements"][kind] += 1
                for reason, count in reasons.items():
                    result["not_split"][reason] += count
                sentences = [claim for claim in claims if claim.kind == SENTENCE]
                if _SPACE.sub("", "".join(claim.text for claim in sentences)) != _SPACE.sub("", body):
                    result["not_covered"].append(statement_id)
                result["split_sentences"][kind] += len({claim.parent for claim in claims if claim.kind == LIST_ITEM})
                for claim in claims:
                    result["claims"][(kind, claim.kind)] += 1
                    if claim.kind == SENTENCE:
                        for cue in claim.cues:
                            result["cues"][cue] += 1
                    feature = None
                    if claim.kind == LIST_ITEM and kind == "symptom":
                        found = names.get(item_name(claim.text), [])
                        result["features"]["one feature" if len(found) == 1 else "several" if found else "none"] += 1
                        feature = found[0] if len(found) == 1 else None
                    parent = claim_id(statement_id, SENTENCE, *claim.parent) if claim.parent else None
                    rows.append(
                        (
                            claim_id(statement_id, claim.kind, claim.start, claim.end),
                            statement_id,
                            parent,
                            claim.kind,
                            claim.start,
                            claim.end,
                            claim.text,
                            claim.rule,
                            json.dumps(claim.cues, sort_keys=True),
                            feature,
                        )
                    )
            cur.execute(
                """CREATE TEMP TABLE tmp_claims (claim_id text, statement_id text, parent_claim_id text, kind text,
                       span_start integer, span_end integer, claim_text text, rule text, cues jsonb,
                       proposed_feature_id text) ON COMMIT DROP"""
            )
            with cur.copy("COPY tmp_claims FROM STDIN") as copy:
                for row in rows:
                    copy.write_row(row)
            # Sentences first: a list item points at the sentence it belongs to.
            for kind in (SENTENCE, LIST_ITEM):
                cur.execute(
                    """INSERT INTO statement_claims (claim_id, statement_id, parent_claim_id, kind, span_start, span_end,
                                                     claim_text, rule, cues, proposed_feature_id)
                       SELECT * FROM tmp_claims WHERE kind = %s ON CONFLICT (claim_id) DO NOTHING""",
                    (kind,),
                )
                result["inserted"] += cur.rowcount
            cur.execute("ANALYZE statement_claims")
            ids = [row[0] for row in statements]
            cur.execute(
                """SELECT count(*), count(*) FILTER (WHERE c.status = 'pending'),
                          count(*) FILTER (WHERE c.status <> 'pending' AND c.reviewer IS NULL),
                          count(*) FILTER (WHERE substr(s.text_content, c.span_start + 1, c.span_end - c.span_start) <> c.claim_text),
                          count(DISTINCT c.statement_id) FILTER (WHERE c.kind = 'sentence'),
                          count(*) FILTER (WHERE c.proposed_feature_id IS NOT NULL),
                          count(*) FILTER (WHERE c.applicability IS NOT NULL),
                          count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM statement_sources x WHERE x.statement_id = c.statement_id))
                   FROM statement_claims c JOIN statements s USING (statement_id) WHERE c.statement_id = ANY(%s)""",
                (ids,),
            )
            keys = (
                "rows",
                "pending",
                "decided_without_reviewer",
                "not_the_text_at_their_span",
                "statements_with_sentences",
                "with_a_proposed_feature",
                "with_applicability",
                "without_a_source",
            )
            result["stored"] = dict(zip(keys, cur.fetchone(), strict=True))
            result["expected_rows"] = len({row[0] for row in rows})
    finally:
        engine.dispose()
    return result


def check(result: dict[str, Any]) -> list[str]:
    """Everything that would be a gap or a claim that is not its statement's own text; empty when there is none."""
    diffs: list[str] = []
    stored, statements = result["stored"], sum(result["statements"].values())
    if result["not_covered"]:
        diffs.append(f"{len(result['not_covered'])} statements whose sentences do not hold all of their text")
    if stored["statements_with_sentences"] != statements:
        diffs.append(f"{statements} statements read, {stored['statements_with_sentences']} have their sentences stored")
    if stored["rows"] < result["expected_rows"]:
        diffs.append(f"{result['expected_rows']} claims made by the rules, {stored['rows']} stored")
    if stored["not_the_text_at_their_span"]:
        diffs.append(
            f"{stored['not_the_text_at_their_span']} stored claims are not their statement's text at their offsets"
        )
    if stored["decided_without_reviewer"]:
        diffs.append(f"{stored['decided_without_reviewer']} claims were decided without a recorded reviewer")
    if stored["without_a_source"]:
        diffs.append(f"{stored['without_a_source']} claims belong to a statement that has no source record")
    return diffs


def report(result: dict[str, Any]) -> list[str]:
    """The lines the command prints."""
    kinds = sorted(result["statements"])
    lines = [f"rules {result['version']}: {sum(result['statements'].values())} statements read"]
    for kind in kinds:
        lines.append(
            f"  {kind}: {result['statements'][kind]} statements, {result['claims'][(kind, SENTENCE)]} sentences, "
            f"{result['split_sentences'][kind]} of them enumerations giving {result['claims'][(kind, LIST_ITEM)]} list items"
        )
    lines.append(f"sentences with a comma left whole, by reason: {dict(sorted(result['not_split'].items()))}")
    lines.append(f"sentences carrying a wording cue: {dict(sorted(result['cues'].items()))}")
    lines.append(
        f"list items of symptom statements, by feature whose name they are exactly: {dict(sorted(result['features'].items()))}"
    )
    lines.append(f"inserted now: {result['inserted']}; stored: {result['stored']}")
    return lines
