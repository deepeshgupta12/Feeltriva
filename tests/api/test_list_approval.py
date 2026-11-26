"""An approval given for whole lists (M2.19): which rows it is entered on, which are set aside and why, and
that entering it records the reviewer and the note on each row and leaves the rest as it was."""

from __future__ import annotations

import subprocess
import sys
import uuid

import pytest
from feeltriva_api import list_approval
from feeltriva_api.auth import Principal
from feeltriva_api.models import (
    Disease,
    DiseaseFeatureEvidence,
    EvidenceChunk,
    Feature,
    KnowledgeRelease,
    MappingRelease,
    RelationSuggestion,
    ReviewNote,
    Statement,
    StatementClaim,
    TerminologyLink,
)
from sqlalchemy import select

WHO = Principal(subject="dev-reviewer:lists", roles=frozenset({"reviewer"}))
NOTE = "Approved for the whole list at once; entered for the reviewer (test)."


@pytest.fixture
def rows(owner_db):
    """Invented rows, one or two of each case the plan tells apart."""
    tag = uuid.uuid4().hex[:8]
    with owner_db.transaction(None, role="migration") as tx:
        tx.add(Disease(disease_id=f"dis_{tag}", preferred_name=f"pretend illness {tag}"))
        for key, name in (
            ("item", f"pretend ache {tag}"),
            ("again", f"pretend ache {tag}.1"),  # a repeated column heading, as a data file gives it
            ("other", f"ache pretend {tag}"),
            ("far", f"pretend lump {tag}"),
        ):
            tx.add(Feature(feature_id=f"feat_{tag}_{key}", preferred_name=name, kind="symptom", value_type="boolean"))
        tx.flush()

        def link(key, system, code, **detail):
            tx.add(
                TerminologyLink(
                    link_id=f"tl_{tag}_{key}",
                    disease_id=f"dis_{tag}",
                    system=system,
                    system_version="t",
                    code=code,
                    title=f"Pretend entry {key} {tag}",
                    uri="u",
                    match_method="exact_title",
                    detail=detail,
                )
            )

        link("general", "ICD-11 MMS", f"Z{tag}")
        link("narrow", "ICD-11 MMS", f"Z{tag}.1")  # lies under the general one
        link("alone", "MONDO", f"MONDO:{tag}")
        link("this", "HPO", f"HP:{tag}1")  # two entries of one list for one name, neither under the other
        link("that", "HPO", f"HP:{tag}2")

        def pair(key, left, right, relation, signals, labels=None):
            tx.add(
                RelationSuggestion(
                    suggestion_id=f"rs_{tag}_{key}",
                    subject_type="feature",
                    relation=relation,
                    left_id=f"feat_{tag}_{left}",
                    right_id=f"feat_{tag}_{right}",
                    left_label=(labels or (f"pretend ache {tag}", ""))[0],
                    right_label=(labels or ("", f"ache pretend {tag}"))[1],
                    signals=signals,
                )
            )

        code = {"signal": "same_standard_code", "vocabulary": "ICD-11 MMS", "code": "X1", "release": "t"}
        pair("words", "item", "other", "possible_synonym", [{"signal": "same_words_other_order_or_number"}, code])
        pair("code", "item", "far", "possible_synonym", [code])
        pair("kind", "far", "item", "possible_subtype", [{"signal": "adds_words", "words": ["x"]}])
        pair("heading", "again", "item", "possible_synonym", [{"signal": "same_words_other_punctuation"}])
        doubt = (f"pretend doubt {tag}", f"pretend other doubt {tag}")
        pair("doubt", "item", "far", "possible_synonym", [{"signal": "same_words_other_punctuation"}], labels=doubt)

        for key, status, disease in (
            ("kept", "pending", f"dis_{tag}"),
            ("copy", "retired", f"dis_{tag}"),
            ("no", "pending", None),
        ):
            tx.add(
                Statement(
                    statement_id=f"st_{tag}_{key}",
                    disease_id=disease,
                    statement_type="symptom",
                    text_content=f"A pretend sentence {key} ({tag}).",
                    status=status,
                )
            )
        tx.flush()
        # A list item belongs to a sentence. The last one the service refuses: its text names no condition.
        for key, statement, parent, feature in (
            ("sentence", "kept", None, None),
            ("of_copy", "copy", None, None),
            ("whole", "no", None, None),
            ("nameless", "no", "whole", f"feat_{tag}_item"),
        ):
            tx.add(
                StatementClaim(
                    claim_id=f"cl_{tag}_{key}",
                    statement_id=f"st_{tag}_{statement}",
                    parent_claim_id=f"cl_{tag}_{parent}" if parent else None,
                    kind="list_item" if parent else "sentence",
                    span_start=0,
                    span_end=5,
                    claim_text="A pre",
                    rule="test",
                    cues={},
                    proposed_feature_id=feature,
                )
            )
            tx.flush()
        for key, kind in (("counted", "dataset_cooccurrence"), ("mention", "narrative_lexical_mention")):
            tx.add(
                DiseaseFeatureEvidence(
                    evidence_id=f"ev_{tag}_{key}",
                    disease_id=f"dis_{tag}",
                    feature_id=f"feat_{tag}_item",
                    statement_id=f"st_{tag}_kept",  # a fact rests on a text or on a source record
                    relationship="sample_relation",
                    context={},
                    evidence_type=kind,
                )
            )
        tx.add(MappingRelease(release_id=f"la-{tag}", version=f"la-{tag}-1"))
        tx.flush()
        tx.add(
            KnowledgeRelease(
                release_id=f"lak-{tag}",
                mapping_release_id=f"la-{tag}",
                version=f"lak-{tag}-0",
                manifest_uri=f"test://lak-{tag}",
            )
        )
        tx.flush()
        tx.add(
            EvidenceChunk(
                chunk_id=f"ch_{tag}_refs",
                statement_id=f"st_{tag}_kept",  # a part of a text rests on a text or on a source record
                knowledge_release_id=f"lak-{tag}",
                chunk_text="References: one, two.",
                details={"boilerplate": True},
            )
        )
    return tag, [{"names": list(doubt), "reason": "not sure (test)", "noted_on": "x"}]


def _mine(planned, tag):
    """The plan cut down to this test's own rows: the test database also holds the real archives and the rows of
    other tests, and none of those may be decided here."""
    return [
        {
            "target_type": entry["target_type"],
            "ids": [row for row in entry["ids"] if tag in row],
            "set_aside": {why: [row for row in found if tag in row] for why, found in entry["set_aside"].items()},
        }
        for entry in planned
    ]


def _short(entry, tag):
    """The rows of one list by the short names the fixture gave them: those for the approval, and those set aside."""
    aside = {why: sorted(row.split(f"{tag}_", 1)[-1] for row in found) for why, found in entry["set_aside"].items()}
    return sorted(row.split(f"{tag}_", 1)[-1] for row in entry["ids"]), {k: v for k, v in aside.items() if v}


def test_the_plan_takes_rows_that_stand_on_their_own_and_sets_the_others_aside_with_the_reason(rows, owner_db):
    tag, exceptions = rows
    with owner_db.transaction(None, role="migration") as tx:
        planned = {entry["target_type"]: entry for entry in _mine(list_approval.plan(tx, exceptions), tag)}
    assert _short(planned["disease"], tag) == ([f"dis_{tag}"], {})
    assert _short(planned["feature"], tag) == (
        ["far", "item", "other"],
        {list_approval.REPEATED_HEADING: ["again"]},
    )
    # The general entry is the default; two entries that are not one under the other are for a person.
    assert _short(planned["terminology_link"], tag) == (
        ["alone", "general"],
        {list_approval.NARROWER: ["narrow"], list_approval.SEVERAL_ENTRIES: ["that", "this"]},
    )
    assert _short(planned["relation_suggestion"], tag) == (
        ["words"],
        {
            list_approval.EXCEPTION: ["doubt"],
            list_approval.KIND_OF: ["kind"],
            list_approval.CODE_ONLY: ["code"],
            list_approval.REPEATED_HEADING: ["heading"],
        },
    )
    assert _short(planned["claim"], tag) == (
        ["nameless", "sentence", "whole"],
        {list_approval.TEXT_RETIRED: ["of_copy"]},
    )
    assert _short(planned["evidence"], tag) == (["counted"], {list_approval.MENTION: ["mention"]})
    assert _short(planned["statement"], tag)[0] == ["kept", "no"]
    assert _short(planned["chunk"], tag) == ([], {list_approval.REFERENCE_LIST: ["refs"]})
    # Suggested matches, rules and questions are never entered for a list.
    assert all(planned[target]["ids"] == [] for target in ("link_proposal", "followup_question", "rule_bundle"))


def test_entering_records_the_reviewer_and_the_note_on_each_row_and_leaves_the_rest_as_it_was(
    rows, owner_db, container
):
    tag, exceptions = rows
    with owner_db.transaction(None, role="migration") as tx:
        planned = _mine(list_approval.plan(tx, exceptions), tag)
    said: list[str] = []
    results = {
        entry["target_type"]: entry
        for entry in list_approval.enter(container.db, WHO, NOTE, planned, progress=said.append)
    }
    assert {
        key: (found["planned"], found["approved"], found["refused"])
        for key, found in results.items()
        if found["planned"]
    } == {
        "disease": (1, 1, {}),
        "feature": (3, 3, {}),
        "statement": (2, 2, {}),
        # The service's own rule still refuses what it refuses, and the row is counted under the rule's code.
        "claim": (3, 2, {"claim_has_no_disease": 1}),
        "evidence": (1, 1, {}),
        "terminology_link": (2, 2, {}),
        "relation_suggestion": (1, 1, {}),
    }
    assert results["claim"]["refused_examples"] == {
        "claim_has_no_disease": "The statement of this claim names no disease."
    }
    assert results["terminology_link"]["set_aside"] == {list_approval.NARROWER: 1, list_approval.SEVERAL_ENTRIES: 2}
    assert "claim: 2 of 3 approved, 1 refused" in said
    with owner_db.transaction(None, role="migration") as tx:
        links = {
            row.link_id.rsplit("_", 1)[1]: (row.status, row.reviewer)
            for row in tx.scalars(select(TerminologyLink).where(TerminologyLink.link_id.like(f"tl_{tag}_%")))
        }
        assert links == {
            "general": ("approved", WHO.subject),
            "alone": ("approved", WHO.subject),
            "narrow": ("pending", None),
            "this": ("pending", None),
            "that": ("pending", None),
        }
        pairs = {
            row.suggestion_id.rsplit("_", 1)[1]: row.status
            for row in tx.scalars(
                select(RelationSuggestion).where(RelationSuggestion.suggestion_id.like(f"rs_{tag}_%"))
            )
        }
        assert pairs == {
            "words": "approved",
            "code": "pending",
            "kind": "pending",
            "heading": "pending",
            "doubt": "pending",
        }
        assert (
            tx.get(Feature, f"feat_{tag}_again").status == "pending"
            and tx.get(Feature, f"feat_{tag}_item").status == "approved"
        )
        assert tx.get(DiseaseFeatureEvidence, f"ev_{tag}_mention").status == "pending"
        assert {
            key: tx.get(StatementClaim, f"cl_{tag}_{key}").status for key in ("sentence", "of_copy", "nameless")
        } == {
            "sentence": "approved",
            "of_copy": "pending",
            "nameless": "pending",
        }
        kept = tx.get(Statement, f"st_{tag}_kept")
        assert (kept.status, kept.reviewed_by) == ("approved", WHO.subject)
        # Every approved row carries the note under the reviewer's name; a row set aside or refused has none.
        notes = tx.scalars(select(ReviewNote).where(ReviewNote.target_id.like(f"%{tag}%"))).all()
        assert len(notes) == 12 and {(note.note, note.reviewer, note.status_change) for note in notes} == {
            (NOTE, WHO.subject, "approved")
        }
        # A second plan has nothing left of what was entered: the approval is not entered twice.
        again = _mine(list_approval.plan(tx, exceptions), tag)
        assert {entry["target_type"]: entry["ids"] for entry in again if entry["ids"]} == {
            "claim": [f"cl_{tag}_nameless"]
        }


def test_run_as_a_command_the_review_service_knows_every_list_and_the_plan_names_them_all(rows, owner_db):
    # Started on its own, as the command is, nothing but the module itself has been loaded.
    check = (
        "from feeltriva_api import list_approval, review; import sys; "
        "sys.exit(len(set(list_approval.TARGETS) - set(review._TARGETS)))"
    )
    assert subprocess.run([sys.executable, "-c", check], check=False).returncode == 0
    tag, exceptions = rows
    with owner_db.transaction(None, role="migration") as tx:
        assert tuple(entry["target_type"] for entry in list_approval.plan(tx, exceptions)) == list_approval.TARGETS
