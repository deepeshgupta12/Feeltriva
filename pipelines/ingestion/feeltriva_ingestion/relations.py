"""Suggested synonyms and subtypes among the candidates (M2.8).

The handoff (`docs/01` section 4, rule 4): "Use casefold/trim/collapse-whitespace only for
initial disease labels. Preserve subtype, acuity and severity distinctions. Suggested synonyms
go to review." So nothing is merged here. This module only proposes pairs, each with the reason
it was proposed, and a reviewer accepts or rejects them.

A pair is proposed as a possible synonym when the two labels

- are the same words once punctuation is ignored (`skin_rash` and `skin rash`);
- are the same words in another order, or in singular and plural (`pain in back`, `back pain`);
- differ only in British or American spelling (`diarrhoea`, `diarrhea`);
- carry a candidate link to the same code of a standard vocabulary (M2.11), unless that code is a
  residual one ("other specified", "unspecified"), which names a category and not a meaning.

A pair is proposed as a possible subtype when one label is the other plus one or two words
(`acute bronchitis` and `bronchitis`). Such a pair is never proposed as a synonym: the extra
word may be exactly the acuity or severity the handoff says to preserve.

Wording is the only evidence. Two labels with the same words can still mean different things,
and two with different words the same thing; that is why every row is `pending`.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from feeltriva_api.settings import Settings
from sqlalchemy import create_engine

from .cases import _raw_cursor
from .meanings import is_question
from .vocabulary import plain, query_for

SYNONYM, SUBTYPE = "possible_synonym", "possible_subtype"
MAX_EXTRA_WORDS = 2
# Words that carry no meaning of their own in a label ("pain in the back").
_FILLER = frozenset({"a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"})
# British spellings written the American way, for comparison only.
_SPELLING = (("oe", "e"), ("ae", "e"))


def _singular(word: str) -> str:
    # "ss", "us" and "is" endings are not plurals: weakness, virus, arthritis.
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")) else word


def content_words(label: str) -> frozenset[str]:
    """The words of a label that carry meaning, in singular form, in no order."""
    return frozenset(_singular(word) for word in plain(label).split() if word not in _FILLER)


def spelling_key(label: str) -> str:
    words = []
    for word in plain(label).split():
        if len(word) >= 6:
            for british, american in _SPELLING:
                word = word.replace(british, american)
        words.append(word)
    return " ".join(words)


def suggestion_id(subject_type: str, relation: str, left: str, right: str) -> str:
    if relation == SYNONYM:
        left, right = sorted((left, right))
    return "rs_" + hashlib.sha256("\x1f".join((subject_type, relation, left, right)).encode()).hexdigest()[:24]


def suggest(subjects: list[dict[str, Any]], codes: dict[str, set[tuple[str, str, str]]]) -> list[dict[str, Any]]:
    """Suggested pairs among subjects of one type.

    subjects: {"id", "label"} per candidate, `label` being the name to compare. codes: candidate ID ->
    the standard codes it is linked to, as (vocabulary, release, code)."""
    by_id = {s["id"]: s for s in subjects}
    found: dict[tuple[str, str, str], list[dict[str, Any]]] = {}

    def add(relation: str, left: str, right: str, signal: dict[str, Any]) -> None:
        if left == right:
            return
        if relation == SYNONYM:
            left, right = sorted((left, right))
        found.setdefault((relation, left, right), []).append(signal)

    def group(key_of: Any, signal: str) -> None:
        """Pairs whose labels share a key. A pair already found by a closer likeness keeps only that one."""
        groups: dict[Any, list[str]] = {}
        for subject in subjects:
            key = key_of(subject)
            if key:
                groups.setdefault(key, []).append(subject["id"])
        for members in groups.values():
            for i, first in enumerate(members):
                for second in members[i + 1 :]:
                    left, right = sorted((first, second))
                    if (SYNONYM, left, right) not in found:
                        add(SYNONYM, left, right, {"signal": signal})

    group(lambda s: plain(s["label"]), "same_words_other_punctuation")
    group(lambda s: content_words(s["label"]), "same_words_other_order_or_number")
    group(lambda s: spelling_key(s["label"]), "british_or_american_spelling")
    by_code: dict[tuple[str, str, str], list[str]] = {}
    for subject_id, linked in codes.items():
        if subject_id in by_id:
            for linked_code in linked:
                by_code.setdefault(linked_code, []).append(subject_id)
    for (system, release, code), members in by_code.items():
        for i, left in enumerate(sorted(members)):
            for right in sorted(members)[i + 1 :]:
                add(
                    SYNONYM,
                    left,
                    right,
                    {"signal": "same_standard_code", "vocabulary": system, "release": release, "code": code},
                )

    by_words: dict[frozenset[str], list[str]] = {}
    for subject in subjects:
        by_words.setdefault(content_words(subject["label"]), []).append(subject["id"])
    for words, narrower_ids in by_words.items():
        for broader_words, broader_ids in by_words.items():
            extra = words - broader_words
            if broader_words and broader_words < words and len(extra) <= MAX_EXTRA_WORDS:
                for narrower in narrower_ids:
                    for broader in broader_ids:
                        add(SUBTYPE, narrower, broader, {"signal": "adds_words", "words": sorted(extra)})

    suggestions = []
    for (relation, left, right), signals in sorted(found.items()):
        unique = [json.loads(s) for s in sorted({json.dumps(signal, sort_keys=True) for signal in signals})]
        suggestions.append(
            {
                "relation": relation,
                "left_id": left,
                "right_id": right,
                "left_label": by_id[left]["shown"],
                "right_label": by_id[right]["shown"],
                "signals": unique,
            }
        )
    return suggestions


def suggest_relations(database_url: str | None = None, source_ids: list[str] | None = None) -> dict[str, Any]:
    """Generate the suggestions and store the new ones as `pending`. A pair that already has a
    row keeps it, with whatever a reviewer decided. source_ids limits the candidates (tests)."""
    if database_url is None:
        app = Settings()
        database_url = app.migration_database_url or app.database_url
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL (or DATABASE_URL) is required")
    scope = "AND m.source_id = ANY(%s)" if source_ids is not None else ""
    params: tuple[Any, ...] = (source_ids,) if source_ids is not None else ()
    engine = create_engine(database_url)
    result: dict[str, Any] = {"suggested": Counter(), "signals": Counter(), "inserted": Counter(), "subjects": {}}
    try:
        with _raw_cursor(engine) as cur:
            cur.execute(
                f"""SELECT DISTINCT d.disease_id, d.preferred_name FROM diseases d JOIN disease_mappings m USING (disease_id)
                    WHERE true {scope}""",  # noqa: S608 - fixed text
                params,
            )
            diseases = [{"id": row[0], "label": row[1], "shown": row[1]} for row in cur.fetchall()]
            cur.execute(
                f"""SELECT f.feature_id, f.preferred_name, max(m.original_term) FROM features f
                    JOIN feature_mappings m USING (feature_id) WHERE true {scope} GROUP BY 1, 2""",  # noqa: S608 - fixed text
                params,
            )
            # A question sentence is not a name; the source's naming words ("symptom", "rare") are not part of one.
            features = [
                {"id": row[0], "label": query_for(row[1]), "shown": row[1]}
                for row in cur.fetchall()
                if not is_question(row[2])
            ]
            # A residual code ("other specified ...", "..., unspecified") is a shared category, not a shared
            # meaning: chronic and diabetic kidney disease can carry the same one. It is not a reason to suggest.
            cur.execute(
                """SELECT coalesce(disease_id, feature_id), system, system_version, code FROM terminology_links
                   WHERE status <> 'rejected' AND NOT coalesce((detail ->> 'residual')::boolean, false)"""
            )
            codes: dict[str, set[tuple[str, str, str]]] = {}
            for subject_id, system, release, code in cur.fetchall():
                codes.setdefault(subject_id, set()).add((system, release, code))
            for subject_type, subjects in (("disease", diseases), ("feature", features)):
                result["subjects"][subject_type] = len(subjects)
                for suggestion in suggest(subjects, codes):
                    relation = suggestion["relation"]
                    result["suggested"][(subject_type, relation)] += 1
                    for signal in suggestion["signals"]:
                        result["signals"][(subject_type, relation, signal["signal"])] += 1
                    cur.execute(
                        """INSERT INTO relation_suggestions (suggestion_id, subject_type, relation, left_id, right_id,
                                                             left_label, right_label, signals)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb) ON CONFLICT (suggestion_id) DO NOTHING""",
                        (
                            suggestion_id(subject_type, relation, suggestion["left_id"], suggestion["right_id"]),
                            subject_type,
                            relation,
                            suggestion["left_id"],
                            suggestion["right_id"],
                            suggestion["left_label"],
                            suggestion["right_label"],
                            json.dumps(suggestion["signals"], sort_keys=True),
                        ),
                    )
                    result["inserted"][(subject_type, relation)] += cur.rowcount
            cur.execute("SELECT status::text, count(*) FROM relation_suggestions GROUP BY 1")
            result["stored"] = dict(cur.fetchall())
    finally:
        engine.dispose()
    return result
