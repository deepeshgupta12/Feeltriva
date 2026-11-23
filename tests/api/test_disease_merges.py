"""Merging and splitting disease labels, with their history (M2.5c1). Invented labels."""

from __future__ import annotations

import uuid

import pytest
from feeltriva_api.models import Disease
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import Api

MERGE = "/internal/v1/review/disease-merges"
SPLIT = "/internal/v1/review/disease-splits"


@pytest.fixture
def reviewer(client) -> Api:
    name = f"rev-{uuid.uuid4().hex[:8]}"
    return Api(client, subject=name, token=f"dev-reviewer:{name}")


@pytest.fixture
def labels(owner_db) -> str:
    """Four invented labels: a kept one, two that name the same thing, and one merged into one of those later."""
    tag = uuid.uuid4().hex[:10]
    with owner_db.transaction(None, role="migration") as tx:
        for key, name in (
            ("kept", "pretend ache"),
            ("alias", "ache, pretend"),
            ("old", "pretended aching"),
            ("far", "aching (pretend)"),
        ):
            tx.add(Disease(disease_id=f"dis_{tag}_{key}", preferred_name=f"{name} {tag}"))
    return tag


def _history(client, who: Api, disease_id: str):
    return client.get(f"/internal/v1/review/diseases/{disease_id}/history", headers=who.headers(None))


def test_a_merge_keeps_one_label_makes_the_other_its_synonym_and_is_recorded(
    client, api: Api, reviewer: Api, labels, owner_db
):
    kept, alias, old = (f"dis_{labels}_{key}" for key in ("kept", "alias", "old"))

    def merge(source, target, who=reviewer, **more):
        body = {"source_disease_id": source, "target_disease_id": target, "note": "They name the same thing.", **more}
        return client.post(MERGE, headers=who.headers(None), json=body)

    assert merge(alias, kept, who=api).status_code == 403 and _history(client, api, kept).status_code == 403
    assert (merge(kept, kept).status_code, merge(f"dis_{labels}_none", kept).status_code) == (422, 404)
    merged = merge(alias, kept)
    assert merged.status_code == 200
    body = merged.json()
    assert body["kept"] == {"disease_id": kept, "preferred_name": f"pretend ache {labels}", "review_status": "pending"}
    assert body["synonyms"] == [f"ache, pretend {labels}"]
    assert body["merged_labels"] == [{"disease_id": alias, "preferred_name": f"ache, pretend {labels}"}]
    with owner_db.transaction(None, role="migration") as tx:
        row = tx.get(Disease, alias)
        # The merged label stays, with its own name, pointing at the kept one.
        assert (row.redirected_to, row.status, row.preferred_name) == (kept, "retired", f"ache, pretend {labels}")
    event = body["history"][0]
    assert (event["action"], event["disease_id"], event["other_id"], event["reviewer"], event["note"]) == (
        "merge",
        alias,
        kept,
        f"dev-reviewer:{reviewer.subject}",
        "They name the same thing.",
    )
    assert event["detail"]["status_before"] == "pending" and event["detail"]["renamed_to"] is None
    # A merged label cannot be merged again, and nothing is merged into a label that is itself merged.
    assert (merge(alias, old).json()["code"], merge(old, alias).json()["code"]) == (
        "already_merged",
        "target_is_merged",
    )
    # Asked for the merged label, the history answers with the kept one.
    assert _history(client, reviewer, alias).json()["kept"]["disease_id"] == kept


def test_the_kept_label_can_take_the_standard_name_and_labels_merged_earlier_follow(
    client, reviewer: Api, labels, owner_db
):
    kept, alias, old, far = (f"dis_{labels}_{key}" for key in ("kept", "alias", "old", "far"))

    def merge(source, target, **more):
        body = {"source_disease_id": source, "target_disease_id": target, "note": "Same thing.", **more}
        return client.post(MERGE, headers=reviewer.headers(None), json=body)

    assert merge(far, old).status_code == 200  # "far" is merged into "old" first
    renamed = merge(old, kept, kept_name=f"Pretend ache syndrome {labels}")
    assert renamed.status_code == 200
    body = renamed.json()
    # The kept label has the standard name; its former name and both merged labels are its synonyms.
    assert body["kept"]["preferred_name"] == f"Pretend ache syndrome {labels}"
    assert sorted(body["synonyms"]) == sorted(
        [f"aching (pretend) {labels}", f"pretended aching {labels}", f"pretend ache {labels}"]
    )
    with owner_db.transaction(None, role="migration") as tx:
        assert {key: tx.get(Disease, key).redirected_to for key in (far, old, alias)} == {
            far: kept,
            old: kept,
            alias: None,
        }
    last = body["history"][-1]
    assert (
        last["detail"]["moved_with_it"] == [far] and last["detail"]["renamed_to"] == f"Pretend ache syndrome {labels}"
    )
    assert merge(alias, kept, kept_name=" ").status_code == 422


def test_a_split_takes_a_merged_label_out_again_and_the_history_keeps_both_events(
    client, reviewer: Api, labels, owner_db
):
    kept, alias = f"dis_{labels}_kept", f"dis_{labels}_alias"
    body = {"source_disease_id": alias, "target_disease_id": kept, "note": "Same thing."}
    assert client.post(MERGE, headers=reviewer.headers(None), json=body).status_code == 200

    def split(disease_id):
        return client.post(
            SPLIT, headers=reviewer.headers(None), json={"disease_id": disease_id, "note": "Not the same after all."}
        )

    assert split(kept).json()["code"] == "not_merged"
    undone = split(alias)
    assert undone.status_code == 200
    after = undone.json()
    assert after["synonyms"] == [] and after["merged_labels"] == []
    assert [event["action"] for event in after["history"]] == ["merge", "split"]
    with owner_db.transaction(None, role="migration") as tx:
        row = tx.get(Disease, alias)
        assert (row.redirected_to, row.status) == (None, "pending")  # it has the status it had before the merge
    assert split(alias).json()["code"] == "not_merged"


@pytest.mark.postgres
def test_the_database_keeps_the_history_unchanged_and_lets_only_a_reviewer_merge(
    client, reviewer: Api, labels, db, owner_db
):
    kept, alias = f"dis_{labels}_kept", f"dis_{labels}_alias"
    body = {"source_disease_id": alias, "target_disease_id": kept, "note": "Same thing."}
    assert client.post(MERGE, headers=reviewer.headers(None), json=body).status_code == 200
    for statement in (
        "UPDATE disease_history SET note = 'x' WHERE disease_id = :d",
        "DELETE FROM disease_history WHERE disease_id = :d",
    ):
        with pytest.raises(DBAPIError, match="cannot be changed"), owner_db.transaction(None, role="migration") as tx:
            tx.execute(text(statement), {"d": alias})
    # A transaction that is not a reviewer's changes no disease; a reviewer's cannot rewrite a definition.
    with db.transaction("someone") as tx:
        assert (
            tx.execute(text("UPDATE diseases SET redirected_to = NULL WHERE disease_id = :d"), {"d": alias}).rowcount
            == 0
        )
    with pytest.raises(DBAPIError), db.transaction("rev", role="reviewer") as tx:
        tx.execute(text("UPDATE diseases SET definition = 'x' WHERE disease_id = :d"), {"d": alias})
    with pytest.raises(DBAPIError), db.transaction("someone") as tx:
        tx.execute(
            text(
                "INSERT INTO disease_history (event_id, action, disease_id, other_id, reviewer, note) "
                "VALUES (gen_random_uuid(), 'merge', :a, :b, 'someone', 'x')"
            ),
            {"a": kept, "b": alias},
        )
