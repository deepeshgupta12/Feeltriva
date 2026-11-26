"""An approval given for whole lists of pending rows, entered row by row under the reviewer's name (M2.19).

A reviewer may approve a list as a whole instead of opening every row. Entering that is not the same as
approving every pending row: an approval given for a list can settle only a row that says one thing on its
own. This module works out which rows those are, sets the others aside with the reason, and records the
approval on each remaining row through the review service, exactly as a decision on one row is recorded:
the service's own rules still refuse what they refuse, and each row carries the note and the reviewer.

Set aside, and left pending (decision E102):

- a row that the stored data itself calls a guess to be looked at: a suggested match that is not an exact
  name, a pair suggested as "a kind of", a pair of item names that share only a code, a fact taken from a
  mention in a text (a mention is not an assertion);
- rows that exclude each other: two entries of one list for one name, where the rule "the general entry is
  the default" does not leave exactly one;
- a row that goes against a decision already recorded: a pair listed in `specs/merge_exceptions.json`, a
  sentence of a text that was retired as a copy;
- a name that is a repeated column heading of a data file, and a pair naming one;
- a part of a text file that is a list of references or links (the service refuses it in any case);
- rules, questions and rule sets: they act on a person's answers and are decided one at a time.

Run without `--approve` it counts and changes nothing. Nothing is published by this module.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Callable
from typing import Any

from sqlalchemy import select

from . import published_knowledge, published_mappings, review_bulk, review_claims, review_proposals, review_rules
from .auth import Principal
from .db import Database
from .duplicates import load_exceptions, plain
from .models import (
    Disease,
    DiseaseFeatureEvidence,
    DiseaseMapping,
    EvidenceChunk,
    Feature,
    FeatureMapping,
    FollowupQuestion,
    LinkProposal,
    RelationSuggestion,
    RuleBundle,
    Statement,
    StatementClaim,
    TerminologyLink,
)
from .review import _lies_under
from .settings import get_settings

# Why a pending row is not decided by an approval given for its whole list.
REPEATED_HEADING = "the name is a repeated column heading of a data file, not an item of its own"
TEXT_RETIRED = "its text was retired as a word-for-word copy of another"
REFERENCE_LIST = "a list of references or links in a text file, not a statement about the condition"
MENTION = "a fact taken from a mention in a text: the row itself records that a mention is not an assertion"
NARROWER = "a more general entry of the same list is the default for this name; this narrower one stays as it is"
SEVERAL_ENTRIES = "one name has more than one entry of the same list, and they are not one under the other"
KIND_OF = "a pair suggested as 'a kind of' only because one name adds words to the other"
CODE_ONLY = "a pair of names that share only a code of a reference list, which can cover different things"
EXCEPTION = "a pair listed as doubtful in specs/merge_exceptions.json"
SUGGESTED = "a suggested match that is not an exact name: each is to be looked at"
NOTES_ONLY = "a record that a name has no match: it takes notes, not a decision"
ONE_AT_A_TIME = "a rule, a question or a rule set acts on a person's answers and is decided one at a time"

_SAME_WORDS = {"same_words_other_punctuation", "same_words_other_order_or_number", "british_or_american_spelling"}
_MENTION_TYPE = "narrative_lexical_mention"
_ICD_MMS = "ICD-11 MMS"
_NUMBERED = re.compile(r"^(.*\S)\s*[. ]\s*\d+$")
BATCH = review_bulk.MAX_ROWS
# The lists, in the order the approval is entered. The review service learns each kind of row from the module that
# holds its rule, so those modules are named here: run as a command, nothing else would have loaded them.
TARGETS = (
    "disease",
    "feature",
    "disease_mapping",
    "feature_mapping",
    "statement",
    "chunk",
    "claim",
    "evidence",
    "terminology_link",
    "relation_suggestion",
    "link_proposal",
    "followup_question",
    "rule_bundle",
)
_RULES_FROM = (published_mappings, published_knowledge, review_claims, review_proposals, review_rules)


def _pending(tx: Any, key: Any, *where: Any) -> list[str]:
    model = key.class_
    return list(tx.scalars(select(key).where(model.status == "pending", *where).order_by(key)).all())


def _features(tx: Any) -> tuple[list[str], dict[str, list[str]]]:
    names = {plain(name) for name in tx.scalars(select(Feature.preferred_name)).all()}
    ids, repeated = [], []
    rows = tx.execute(
        select(Feature.feature_id, Feature.preferred_name)
        .where(Feature.status == "pending")
        .order_by(Feature.feature_id)
    ).all()
    for feature_id, name in rows:
        numbered = _NUMBERED.match(name)
        if numbered and plain(numbered.group(1)) in names:
            repeated.append(feature_id)
        else:
            ids.append(feature_id)
    return ids, {REPEATED_HEADING: repeated}


def _chunks(tx: Any) -> tuple[list[str], dict[str, list[str]]]:
    ids: list[str] = []
    lists: list[str] = []
    rows = tx.execute(
        select(EvidenceChunk.chunk_id, EvidenceChunk.details)
        .where(EvidenceChunk.status == "pending")
        .order_by(EvidenceChunk.chunk_id)
    ).all()
    for chunk_id, details in rows:
        (lists if (details or {}).get("boilerplate") else ids).append(chunk_id)
    return ids, {REFERENCE_LIST: lists}


def _links(tx: Any) -> tuple[list[str], dict[str, list[str]]]:
    groups: dict[tuple[str, str], list[TerminologyLink]] = {}
    live = tx.scalars(
        select(TerminologyLink)
        .where(TerminologyLink.status.in_(("pending", "approved")))
        .order_by(TerminologyLink.link_id)
    ).all()
    for link in live:
        groups.setdefault((link.disease_id or link.feature_id or "", link.system), []).append(link)
    ids: list[str] = []
    aside: dict[str, list[str]] = {NARROWER: [], SEVERAL_ENTRIES: []}
    for (_subject, system), links in groups.items():
        pending = [link for link in links if link.status == "pending"]
        if len(links) == 1:
            ids.extend(link.link_id for link in pending)
            continue
        tops = [
            link
            for link in links
            if system != _ICD_MMS or not any(_lies_under(link, other) for other in links if other is not link)
        ]
        if len(tops) == 1:
            ids.extend(link.link_id for link in pending if link is tops[0])
            aside[NARROWER].extend(link.link_id for link in pending if link is not tops[0])
        else:
            aside[SEVERAL_ENTRIES].extend(link.link_id for link in pending)
    return sorted(ids), aside


def _pairs(tx: Any, exceptions: list[dict[str, Any]], repeated: set[str]) -> tuple[list[str], dict[str, list[str]]]:
    doubtful = {frozenset(plain(name) for name in entry["names"]) for entry in exceptions}
    ids: list[str] = []
    aside: dict[str, list[str]] = {EXCEPTION: [], KIND_OF: [], CODE_ONLY: [], REPEATED_HEADING: []}
    rows = tx.scalars(
        select(RelationSuggestion)
        .where(RelationSuggestion.status == "pending")
        .order_by(RelationSuggestion.suggestion_id)
    ).all()
    for row in rows:
        signals = {entry.get("signal") for entry in row.signals or []}
        if frozenset((plain(row.left_label), plain(row.right_label))) in doubtful:
            aside[EXCEPTION].append(row.suggestion_id)
        elif row.relation != "possible_synonym":
            aside[KIND_OF].append(row.suggestion_id)
        elif row.left_id in repeated or row.right_id in repeated:
            aside[REPEATED_HEADING].append(row.suggestion_id)
        elif not signals & _SAME_WORDS:
            aside[CODE_ONLY].append(row.suggestion_id)
        else:
            ids.append(row.suggestion_id)
    return ids, aside


def plan(tx: Any, exceptions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """For each list, in the order the approval is entered: the rows it is entered on, and the rows set aside
    with the reason. Reads only."""
    retired_text = select(Statement.statement_id).where(Statement.status == "retired")
    confirmable = LinkProposal.code.is_not(None) & LinkProposal.basis.in_(review_proposals.CONFIRMABLE)
    features, features_aside = _features(tx)
    chunks, chunks_aside = _chunks(tx)
    links, links_aside = _links(tx)
    pairs, pairs_aside = _pairs(tx, exceptions, set(features_aside[REPEATED_HEADING]))
    lists: list[tuple[str, list[str], dict[str, list[str]]]] = [
        ("disease", _pending(tx, Disease.disease_id, Disease.redirected_to.is_(None)), {}),
        ("feature", features, features_aside),
        ("disease_mapping", _pending(tx, DiseaseMapping.mapping_id), {}),
        ("feature_mapping", _pending(tx, FeatureMapping.mapping_id), {}),
        ("statement", _pending(tx, Statement.statement_id), {}),
        ("chunk", chunks, chunks_aside),
        (
            "claim",
            _pending(tx, StatementClaim.claim_id, StatementClaim.statement_id.not_in(retired_text)),
            {TEXT_RETIRED: _pending(tx, StatementClaim.claim_id, StatementClaim.statement_id.in_(retired_text))},
        ),
        (
            "evidence",
            _pending(tx, DiseaseFeatureEvidence.evidence_id, DiseaseFeatureEvidence.evidence_type != _MENTION_TYPE),
            {
                MENTION: _pending(
                    tx, DiseaseFeatureEvidence.evidence_id, DiseaseFeatureEvidence.evidence_type == _MENTION_TYPE
                )
            },
        ),
        ("terminology_link", links, links_aside),
        ("relation_suggestion", pairs, pairs_aside),
        (
            "link_proposal",
            [],
            {
                SUGGESTED: _pending(tx, LinkProposal.proposal_id, confirmable),
                NOTES_ONLY: _pending(tx, LinkProposal.proposal_id, ~confirmable),
            },
        ),
        ("followup_question", [], {ONE_AT_A_TIME: _pending(tx, FollowupQuestion.question_id)}),
        ("rule_bundle", [], {ONE_AT_A_TIME: _pending(tx, RuleBundle.bundle_id)}),
    ]
    return [
        {"target_type": target, "ids": ids, "set_aside": {why: rows for why, rows in aside.items() if rows}}
        for target, ids, aside in lists
    ]


def enter(
    db: Database,
    principal: Principal,
    note: str,
    planned: list[dict[str, Any]],
    *,
    progress: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Record "approved" with the note on every planned row, one row at a time. A row the service's rules refuse
    is left as it was and counted under the rule's code, with the first messages as examples."""
    results = []
    for entry in planned:
        decided, codes = 0, Counter[str]()
        examples: dict[str, str] = {}
        ids = entry["ids"]
        for start in range(0, len(ids), BATCH):
            done = review_bulk.decide_each(
                db,
                principal,
                target_type=entry["target_type"],
                target_ids=ids[start : start + BATCH],
                note=note,
                status="approved",
            )
            decided += done["decided"]
            for refusal in done["refused"]:
                codes[refusal["code"]] += 1
                examples.setdefault(refusal["code"], refusal["message"])
        results.append(
            {
                "target_type": entry["target_type"],
                "planned": len(ids),
                "approved": decided,
                "refused": dict(sorted(codes.items())),
                "refused_examples": examples,
                "set_aside": {why: len(rows) for why, rows in entry["set_aside"].items()},
            }
        )
        if progress:
            progress(f"{entry['target_type']}: {decided} of {len(ids)} approved, {sum(codes.values())} refused")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(prog="feeltriva_api.list_approval")
    parser.add_argument("--approve", action="store_true", help="enter the approval (without it nothing is changed)")
    parser.add_argument("--reviewer", help="the name of the reviewer who gave the approval (with --approve)")
    parser.add_argument("--note", help="the note recorded on every row: who approved, how, and who entered it")
    parser.add_argument("--only", action="append", help="one list by its target type; may be given more than once")
    args = parser.parse_args()
    settings = get_settings()
    owner = Database(settings.migration_database_url or settings.database_url)
    with owner.transaction(None, role="migration") as tx:
        planned = plan(tx, load_exceptions())
    if args.only:
        planned = [entry for entry in planned if entry["target_type"] in args.only]
    for entry in planned:
        print(f"{entry['target_type']}: {len(entry['ids'])} rows for the approval")
        for why, rows in entry["set_aside"].items():
            print(f"  set aside, {len(rows)}: {why}")
    if not args.approve:
        print("nothing was changed (run with --approve, --reviewer and --note to enter the approval)")
        return 0
    if not args.reviewer or not args.note:
        print("--approve needs --reviewer and --note")
        return 2
    principal = Principal(subject=f"dev-reviewer:{args.reviewer}", roles=frozenset({"reviewer"}))
    results = enter(Database(settings.database_url), principal, args.note, planned, progress=print)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
