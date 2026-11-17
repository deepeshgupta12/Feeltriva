"""Proposed disease-feature evidence (M1.11). Everything written here is `pending`.

Two different kinds of proposal, never mixed (handoff: "These are different relationships;
co-occurrence alone is not clinical proof"):

1. `narrative_lexical_mention` - a known feature term occurs in an archive-13 symptom
   statement about a disease. Provenance is the statement. A mention is not an assertion:
   the sentence may negate the term or describe someone else, so each proposal records its
   text span and whether a negation cue precedes it. Splitting statements into atomic,
   reviewed claims is a later step (M2.6).

2. `dataset_cooccurrence` - within ONE source file, how many cases carrying a disease label
   also have a feature affirmed. Stored with its denominator as a sample count of that file.
   It is never prevalence: the files' origin, sampling and duplicates are unreviewed, so the
   number of exact-duplicate rows and of distinct profiles behind each denominator is stored
   beside it. Provenance is a whole-file record of the source. Sources are never pooled.

Only pairs that actually occur are stored. A pair that never occurs gets no row: absence of
co-occurrence in a sample is not evidence of absence.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from feeltriva_api.settings import Settings
from sqlalchemy import create_engine

from .archives import Manifest, load_manifest
from .cases import _raw_cursor, case_files
from .load import source_id

NARRATIVE_TYPE = "narrative_lexical_mention"
NARRATIVE_RELATIONSHIP = "mentioned_in_symptom_statement"
COOCCURRENCE_TYPE = "dataset_cooccurrence"
COOCCURRENCE_RELATIONSHIP = "co_occurs_in_source_sample"
WHOLE_FILE_FLAG = "whole_file_record"
MIN_TERM_LENGTH = 3

_QUESTION_TERM = re.compile(r"^e \d+ ")  # archive-15 questionnaire items never occur in prose
_SENTENCE_BREAK = re.compile(r"[.!?;\n]")
_NEGATION = re.compile(
    r"\b(no|not|without|never|absent|absence of|rarely|neither|nor|free of|rule out|ruled out|lack of)\b", re.I
)


def narrative_evidence_id(statement_id: str, feature_id: str) -> str:
    return "ev_" + hashlib.sha256("\x1f".join(("narrative", statement_id, feature_id)).encode()).hexdigest()[:24]


def whole_file_record_id(sid: str) -> str:
    return "recf_" + sid.removeprefix("src_")


def term_pattern(terms: list[str]) -> re.Pattern[str]:
    """Whole-phrase, case-insensitive match of any term; the longest term wins at a position, so
    "chest pain" does not also propose "pain" for the same words."""
    ordered = sorted(set(terms), key=lambda t: (-len(t), t))
    body = "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in ordered)
    return re.compile(rf"(?<![A-Za-z0-9])(?:{body})(?![A-Za-z0-9])", re.I)


def find_mentions(text: str, pattern: re.Pattern[str], feature_by_term: dict[str, str]) -> dict[str, dict[str, Any]]:
    """feature_id -> first span, matched wording, number of mentions and a negation-cue flag."""
    found: dict[str, dict[str, Any]] = {}
    for match in pattern.finditer(text):
        feature_id = feature_by_term.get(" ".join(match.group(0).casefold().split()))
        if feature_id is None:
            continue
        sentence_start = max((m.end() for m in _SENTENCE_BREAK.finditer(text, 0, match.start())), default=0)
        negated = bool(_NEGATION.search(text, sentence_start, match.start()))
        entry = found.get(feature_id)
        if entry is None:
            found[feature_id] = {
                "span": [match.start(), match.end()],
                "matched_text": match.group(0),
                "mentions": 1,
                "negation_cue_before_in_sentence": negated,
            }
        else:
            entry["mentions"] += 1
            entry["negation_cue_before_in_sentence"] = entry["negation_cue_before_in_sentence"] or negated
    return found


def _load_narrative(cur: Any, narrative_sources: list[str]) -> dict[str, int]:
    cur.execute("SELECT feature_id, preferred_name FROM features WHERE feature_id LIKE 'feat\\_%%'")
    feature_by_term = {
        name: feature_id
        for feature_id, name in cur.fetchall()
        if len(name) >= MIN_TERM_LENGTH and not _QUESTION_TERM.match(name)
    }
    totals = {
        "statements": 0,
        "statements_with_mentions": 0,
        "mentions": 0,
        "proposals": 0,
        "proposals_inserted": 0,
        "with_negation_cue": 0,
    }
    if not feature_by_term:
        return totals
    pattern = term_pattern(list(feature_by_term))
    cur.execute(
        """SELECT DISTINCT st.statement_id, st.disease_id, st.text_content
           FROM statements st JOIN statement_sources ss USING (statement_id)
           JOIN source_records r USING (record_id)
           WHERE st.statement_type = 'symptom' AND st.disease_id IS NOT NULL AND r.source_id = ANY(%s)
           ORDER BY st.statement_id""",
        (narrative_sources,),
    )
    for statement_id, disease_id, text in cur.fetchall():
        totals["statements"] += 1
        mentions = find_mentions(text, pattern, feature_by_term)
        if mentions:
            totals["statements_with_mentions"] += 1
        for feature_id, detail in mentions.items():
            totals["mentions"] += detail["mentions"]
            totals["proposals"] += 1
            totals["with_negation_cue"] += detail["negation_cue_before_in_sentence"]
            context = {
                **detail,
                "match_rule": "whole phrase, case-insensitive, longest term wins",
                "a_mention_is_not_an_assertion": True,
            }
            cur.execute(
                """INSERT INTO disease_feature_evidence (evidence_id, disease_id, feature_id, statement_id,
                       relationship, context, evidence_type, status)
                   VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, 'pending') ON CONFLICT DO NOTHING""",
                (
                    narrative_evidence_id(statement_id, feature_id),
                    disease_id,
                    feature_id,
                    statement_id,
                    NARRATIVE_RELATIONSHIP,
                    json.dumps(context),
                    NARRATIVE_TYPE,
                ),
            )
            totals["proposals_inserted"] += cur.rowcount
    return totals


def _load_cooccurrence(cur: Any, sources: list[tuple[str, str, str]]) -> dict[str, Any]:
    """sources: (source_id, archive, file) of every case file."""
    source_ids = [sid for sid, _, _ in sources]
    cur.execute("SET LOCAL work_mem = '256MB'")
    for sid, archive, file in sources:  # provenance for a whole-file aggregate
        cur.execute(
            """INSERT INTO source_records (record_id, source_id, file_path, row_number, content_hash,
                                           raw_object_uri, quality_flags)
               SELECT %s, s.source_id, %s, NULL, s.sha256, %s, %s::jsonb FROM sources s WHERE s.source_id = %s
               ON CONFLICT DO NOTHING""",
            (whole_file_record_id(sid), file, f"zip://{archive}#{file}", json.dumps([WHOLE_FILE_FLAG]), sid),
        )
    cur.execute(
        """CREATE TEMP TABLE tmp_den ON COMMIT DROP AS
           SELECT r.source_id, l.disease_id, count(*) AS cases,
                  count(DISTINCT c.profile_cluster_id) AS profiles,
                  count(*) FILTER (WHERE c.duplicate_status = 'exact_duplicate_row') AS exact_duplicate_rows
           FROM dataset_cases c JOIN source_records r USING (record_id) JOIN case_labels l USING (case_id)
           WHERE r.source_id = ANY(%s) GROUP BY 1, 2""",
        (source_ids,),
    )
    # One pass over the feature rows. Each row is one (case, column or list term).
    cur.execute(
        """CREATE TEMP TABLE tmp_num ON COMMIT DROP AS
           SELECT fm.source_id, l.disease_id, fm.feature_id,
                  count(*) FILTER (WHERE cf.presence = 'present') AS cases_with,
                  count(*) FILTER (WHERE cf.conflict) AS cases_conflict
           FROM case_features cf JOIN feature_mappings fm USING (mapping_id) JOIN case_labels l USING (case_id)
           WHERE fm.source_id = ANY(%s) AND fm.feature_id IS NOT NULL
           GROUP BY 1, 2, 3""",
        (source_ids,),
    )
    # A feature reached through several columns of one file (repeated headers) would count a case
    # once per column. Recount those features per distinct case.
    cur.execute(
        """CREATE TEMP TABLE tmp_multi ON COMMIT DROP AS
           SELECT mapping_id, source_id, feature_id FROM feature_mappings
           WHERE source_id = ANY(%s) AND (source_id, feature_id) IN (
               SELECT source_id, feature_id FROM feature_mappings
               WHERE source_id = ANY(%s) AND feature_id IS NOT NULL GROUP BY 1, 2 HAVING count(*) > 1)""",
        (source_ids, source_ids),
    )
    cur.execute(
        """UPDATE tmp_num n SET cases_with = d.cases_with, cases_conflict = d.cases_conflict
           FROM (SELECT m.source_id, l.disease_id, m.feature_id,
                        count(DISTINCT cf.case_id) FILTER (WHERE cf.presence = 'present') AS cases_with,
                        count(DISTINCT cf.case_id) FILTER (WHERE cf.conflict) AS cases_conflict
                 FROM case_features cf JOIN tmp_multi m USING (mapping_id) JOIN case_labels l USING (case_id)
                 GROUP BY 1, 2, 3) d
           WHERE n.source_id = d.source_id AND n.disease_id = d.disease_id AND n.feature_id = d.feature_id"""
    )
    recounted = cur.rowcount
    cur.execute(
        """INSERT INTO disease_feature_evidence (evidence_id, disease_id, feature_id, record_id, relationship,
               context, frequency, frequency_denominator, evidence_type, status)
           SELECT 'ev_' || substr(encode(sha256(convert_to(
                      'cooccurrence' || chr(31) || n.source_id || chr(31) || n.disease_id || chr(31) || n.feature_id,
                      'UTF8')), 'hex'), 1, 24),
                  n.disease_id, n.feature_id, 'recf_' || substr(n.source_id, 5), %s,
                  jsonb_build_object(
                      'source', s.source_name, 'cases_with_feature', n.cases_with, 'cases_with_label', d.cases,
                      'distinct_profiles_with_label', d.profiles,
                      'exact_duplicate_rows_with_label', d.exact_duplicate_rows,
                      'cases_with_conflicting_values', n.cases_conflict,
                      'sample_count_not_prevalence', true, 'feature_meaning', 'unclassified',
                      'zero_meaning', 'unknown', 'sources_pooled', false),
                  round(n.cases_with::numeric / d.cases, 6), d.cases, %s, 'pending'
           FROM tmp_num n JOIN tmp_den d USING (source_id, disease_id) JOIN sources s USING (source_id)
           WHERE n.cases_with > 0
           ON CONFLICT DO NOTHING""",
        (COOCCURRENCE_RELATIONSHIP, COOCCURRENCE_TYPE),
    )
    inserted = cur.rowcount
    cur.execute(
        """SELECT s.source_name, count(*) FILTER (WHERE n.cases_with > 0), coalesce(sum(n.cases_with), 0),
                  (SELECT count(*) FROM tmp_den d WHERE d.source_id = n.source_id),
                  (SELECT count(*) FROM tmp_multi m WHERE m.source_id = n.source_id)
           FROM tmp_num n JOIN sources s USING (source_id) GROUP BY s.source_name, n.source_id ORDER BY 1"""
    )
    per_source = {
        name: {
            "pairs": pairs,
            "sum_cases_with_feature": int(total),
            "labels": labels,
            "columns_sharing_a_feature": multi,
        }
        for name, pairs, total, labels, multi in cur.fetchall()
    }
    # Independent count of affirmed feature rows per source, with no label join.
    cur.execute(
        """SELECT s.source_name, count(*) FROM case_features cf JOIN feature_mappings fm USING (mapping_id)
           JOIN sources s ON s.source_id = fm.source_id
           WHERE fm.source_id = ANY(%s) AND cf.presence = 'present' GROUP BY 1""",
        (source_ids,),
    )
    for name, rows in cur.fetchall():
        per_source.setdefault(
            name, {"pairs": 0, "sum_cases_with_feature": 0, "labels": 0, "columns_sharing_a_feature": 0}
        )["affirmed_feature_rows"] = rows
    return {"proposals_inserted": inserted, "pairs_recounted_for_repeated_columns": recounted, "per_source": per_source}


def summarise(cur: Any) -> dict[str, Any]:
    cur.execute(
        """SELECT evidence_type, count(*), count(*) FILTER (WHERE status <> 'pending'),
                  count(*) FILTER (WHERE statement_id IS NULL AND record_id IS NULL),
                  count(*) FILTER (WHERE frequency IS NOT NULL AND frequency_denominator IS NULL),
                  count(*) FILTER (WHERE frequency IS NOT NULL AND (frequency <= 0 OR frequency > 1)),
                  count(DISTINCT (disease_id, feature_id))
           FROM disease_feature_evidence GROUP BY 1 ORDER BY 1"""
    )
    keys = (
        "rows",
        "not_pending",
        "without_provenance",
        "frequency_without_denominator",
        "frequency_out_of_range",
        "distinct_disease_feature_pairs",
    )
    return {row[0]: dict(zip(keys, row[1:], strict=True)) for row in cur.fetchall()}


def load_evidence(
    database_url: str | None = None, manifest: Manifest | None = None, narrative_sources: list[str] | None = None
) -> dict[str, Any]:
    """Write both kinds of proposal. Reads only the database; re-running inserts nothing."""
    if database_url is None:
        settings = Settings()
        database_url = settings.migration_database_url or settings.database_url
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL (or DATABASE_URL) is required")
    manifest = manifest or load_manifest()
    if narrative_sources is None:
        narrative_sources = [source_id("archive(13).zip", "symptoms.csv")]
    sources = [(source_id(f["archive"], f["file"]), f["archive"], f["file"]) for f in case_files(manifest)]
    engine = create_engine(database_url)
    with _raw_cursor(engine) as cur:
        result: dict[str, Any] = {"narrative": _load_narrative(cur, narrative_sources)}
        result["cooccurrence"] = _load_cooccurrence(cur, sources)
        result["stored"] = summarise(cur)
    engine.dispose()
    return result


def check(result: dict[str, Any]) -> list[str]:
    """Internal consistency of what was written. Empty = consistent."""
    diffs = []
    for evidence_type, stored in result["stored"].items():
        for key in ("not_pending", "without_provenance", "frequency_without_denominator", "frequency_out_of_range"):
            if stored[key]:
                diffs.append(f"{evidence_type}: {stored[key]} rows {key.replace('_', ' ')}")
    for name, source in result["cooccurrence"]["per_source"].items():
        affirmed = source.get("affirmed_feature_rows", 0)
        if source["columns_sharing_a_feature"] == 0 and source["sum_cases_with_feature"] != affirmed:
            # Without repeated columns every affirmed feature row is exactly one (case, feature).
            diffs.append(
                f"{name}: co-occurrence counts sum to {source['sum_cases_with_feature']}, "
                f"but {affirmed} affirmed feature rows exist"
            )
        if source["sum_cases_with_feature"] > affirmed:
            diffs.append(f"{name}: co-occurrence counts exceed the affirmed feature rows")
    return diffs
