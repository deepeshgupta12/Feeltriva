"""Suggested synonyms and subtypes in the review queue (M2.8)."""

from __future__ import annotations

import os
import uuid

import pytest
from feeltriva_api.models import Disease, DiseaseMapping, MappingRelease, RelationSuggestion, Source
from sqlalchemy import select, text

from tests.conftest import Api

PATH = "/internal/v1/review/relation-suggestions"


@pytest.fixture
def reviewer(client) -> Api:
    name = f"rev-{uuid.uuid4().hex[:8]}"
    return Api(client, subject=name, token=f"dev-reviewer:{name}")


@pytest.fixture
def suggestion(owner_db):
    tag = uuid.uuid4().hex[:10]
    with owner_db.transaction(None) as tx:
        tx.add(
            RelationSuggestion(
                suggestion_id=f"rs_{tag}",
                subject_type="disease",
                relation="possible_synonym",
                left_id=f"dis_{tag}_a",
                right_id=f"dis_{tag}_b",
                left_label=f"skin_rash {tag}",
                right_label=f"skin rash {tag}",
                signals=[{"signal": "same_words_other_punctuation"}],
            )
        )
    return tag


def test_suggestions_are_listed_for_reviewers_only_with_both_terms_and_the_reason(
    client, api: Api, reviewer: Api, suggestion
):
    assert client.get(PATH).status_code == 401
    assert client.get(PATH, headers=api.headers(None)).status_code == 403
    body = client.get(PATH, params={"q": suggestion}, headers=reviewer.headers(None)).json()
    assert body["total"] == 1 and "nothing is merged until a reviewer decides" in body["label"]
    item = body["items"][0]
    assert (item["left"]["term"], item["right"]["term"]) == (f"skin_rash {suggestion}", f"skin rash {suggestion}")
    assert item["relation"] == "possible_synonym" and item["signals"] == [{"signal": "same_words_other_punctuation"}]
    assert (item["review_status"], item["reviewer"]) == ("pending", None)
    filtered = {"q": suggestion, "relation": "possible_subtype"}
    assert client.get(PATH, params=filtered, headers=reviewer.headers(None)).json()["total"] == 0
    assert "relation_suggestions" in client.get("/internal/v1/review/overview", headers=reviewer.headers(None)).json()


def test_a_rejection_is_recorded_with_the_reviewer_and_changes_nothing_else(
    client, reviewer: Api, suggestion, owner_db
):
    decision = {
        "target_type": "relation_suggestion",
        "target_id": f"rs_{suggestion}",
        "note": "Different conditions.",
        "status": "rejected",
    }
    r = client.post("/internal/v1/review/decisions", headers=reviewer.headers(None), json=decision)
    assert r.status_code == 200 and (r.json()["previous_status"], r.json()["review_status"]) == ("pending", "rejected")
    listed = client.get(PATH, params={"q": suggestion, "status": "rejected"}, headers=reviewer.headers(None)).json()
    assert listed["total"] == 1 and listed["items"][0]["reviewer"] == f"dev-reviewer:{reviewer.subject}"
    with owner_db.transaction(None) as tx:
        stored = tx.execute(
            select(RelationSuggestion).where(RelationSuggestion.suggestion_id == f"rs_{suggestion}")
        ).scalar_one()
        assert (stored.status, stored.reviewer, stored.left_label) == (
            "rejected",
            f"dev-reviewer:{reviewer.subject}",
            f"skin_rash {suggestion}",
        )
    missing = {**decision, "target_id": "rs_missing"}
    assert client.post("/internal/v1/review/decisions", headers=reviewer.headers(None), json=missing).status_code == 404


@pytest.mark.postgres
def test_generated_suggestions_are_stored_pending_and_a_decision_survives_a_rerun(client, reviewer: Api, owner_db, db):
    from feeltriva_ingestion.load import RELEASE_ID, source_id
    from feeltriva_ingestion.relations import suggest_relations

    tag = uuid.uuid4().hex[:10]
    sid = source_id(f"relations-{tag}.zip", "data.csv")
    labels = [f"skin_rash {tag}", f"skin rash {tag}", f"acute bronchitis {tag}", f"bronchitis {tag}", f"cough {tag}"]
    labels += [f"heart attack {tag}", f"myocardial infarction {tag}", f"alpha disease {tag}", f"beta disorder {tag}"]
    with owner_db.transaction(None) as tx:
        if tx.get(MappingRelease, RELEASE_ID) is None:
            tx.add(MappingRelease(release_id=RELEASE_ID, version="lexical-0"))
        tx.add(Source(source_id=sid, source_name=f"relations-{tag}.zip/data.csv", version="t", sha256="0"))
        for n, label in enumerate(labels):
            tx.add(Disease(disease_id=f"dis_{tag}_{n}", preferred_name=label))
        tx.flush()
        for n, label in enumerate(labels):
            tx.add(
                DiseaseMapping(
                    mapping_id=f"dm_{tag}_{n}",
                    release_id=RELEASE_ID,
                    source_id=sid,
                    original_label=label,
                    disease_id=f"dis_{tag}_{n}",
                    method="lexical_casefold_whitespace",
                )
            )
        tx.flush()
        # Candidate links (M2.11): two labels with one specific code, two with one residual code.
        for n, code, residual in (
            (5, f"S{tag}", "false"),
            (6, f"S{tag}", "false"),
            (7, f"R{tag}.Z", "true"),
            (8, f"R{tag}.Z", "true"),
        ):
            tx.execute(
                text(
                    """INSERT INTO terminology_links (link_id, disease_id, system, system_version, code, title, uri, match_method, detail)
                       VALUES (:l, :d, 'ICD-11 MMS', 'test', :c, 't', 'u', 'exact_title', jsonb_build_object('residual', CAST(:r AS boolean)))"""
                ),
                {"l": f"tl_{tag}_{n}", "d": f"dis_{tag}_{n}", "c": code, "r": residual},
            )
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    first = suggest_relations(url, [sid])
    assert first["subjects"] == {"disease": 9, "feature": 0}
    assert dict(first["inserted"]) == {("disease", "possible_synonym"): 2, ("disease", "possible_subtype"): 1}
    listed = client.get(PATH, params={"q": tag, "limit": 10}, headers=reviewer.headers(None)).json()
    found = {(i["relation"], i["left"]["term"], i["right"]["term"]): i for i in listed["items"]}
    assert set(found) == {
        ("possible_synonym", f"skin_rash {tag}", f"skin rash {tag}"),
        ("possible_subtype", f"acute bronchitis {tag}", f"bronchitis {tag}"),  # the narrower term is on the left
        ("possible_synonym", f"heart attack {tag}", f"myocardial infarction {tag}"),  # one specific standard code
    }  # the two labels that share only a residual code are not suggested
    assert (
        found[("possible_synonym", f"heart attack {tag}", f"myocardial infarction {tag}")]["signals"][0]["signal"]
        == "same_standard_code"
    )
    assert all(i["review_status"] == "pending" for i in listed["items"])
    synonym = found[("possible_synonym", f"skin_rash {tag}", f"skin rash {tag}")]["suggestion_id"]
    decision = {
        "target_type": "relation_suggestion",
        "target_id": synonym,
        "note": "Not the same.",
        "status": "rejected",
    }
    assert (
        client.post("/internal/v1/review/decisions", headers=reviewer.headers(None), json=decision).status_code == 200
    )
    again = suggest_relations(url, [sid])
    assert sum(again["inserted"].values()) == 0  # nothing is suggested twice
    with owner_db.transaction(None) as tx:
        assert (
            tx.execute(
                text("SELECT status::text FROM relation_suggestions WHERE suggestion_id = :s"), {"s": synonym}
            ).scalar_one()
            == "rejected"
        )
        merged = tx.execute(
            text("SELECT count(*) FROM diseases WHERE disease_id LIKE :p AND redirected_to IS NOT NULL"),
            {"p": f"dis_{tag}_%"},
        ).scalar_one()
    assert merged == 0  # a suggestion never merges anything
    with db.transaction(
        "dev:someone", role="user"
    ) as tx:  # outside a reviewer transaction the rows cannot be seen or changed
        assert (
            tx.execute(
                text("SELECT count(*) FROM relation_suggestions WHERE suggestion_id = :s"), {"s": synonym}
            ).scalar_one()
            == 0
        )
        assert (
            tx.execute(
                text("UPDATE relation_suggestions SET status = 'approved' WHERE suggestion_id = :s"), {"s": synonym}
            ).rowcount
            == 0
        )
