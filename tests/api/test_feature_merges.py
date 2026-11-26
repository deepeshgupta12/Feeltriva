"""Merging and splitting the names of symptoms and other items, with their history (M2.20). Invented names."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from feeltriva_api import item_duplicates, published_knowledge, published_mappings
from feeltriva_api.auth import Principal
from feeltriva_api.models import (
    ClinicalRule,
    Disease,
    DiseaseFeatureEvidence,
    Feature,
    FeatureMapping,
    KnowledgeRelease,
    MappingRelease,
    RelationSuggestion,
    RuleBundle,
    Source,
    SourceRecord,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import Api

MERGE = "/internal/v1/review/feature-merges"
SPLIT = "/internal/v1/review/feature-splits"
DECIDE = "/internal/v1/review/decisions"


@pytest.fixture
def reviewer(client) -> Api:
    name = f"rev-{uuid.uuid4().hex[:8]}"
    return Api(client, subject=name, token=f"dev-reviewer:{name}")


@pytest.fixture
def items(owner_db) -> str:
    """Invented items: a kept one, two other names for it, one that holds a number, and one a rule names."""
    tag = uuid.uuid4().hex[:10]
    with owner_db.transaction(None, role="migration") as tx:
        for key, name, value_type, aliases in (
            ("kept", "pretend ache", "boolean", ["made-up ache"]),
            ("alias", "pretend-ache", "boolean", ["ache (pretended)"]),
            ("old", "aching pretend", "boolean", []),
            ("number", "pretend ache count", "number", []),
            ("ruled", "pretend ache of the rule", "boolean", []),
        ):
            tx.add(
                Feature(
                    feature_id=f"feat_{tag}_{key}",
                    preferred_name=f"{name} {tag}",
                    kind="symptom",
                    value_type=value_type,
                    aliases=aliases,
                )
            )
        tx.add(
            RuleBundle(
                bundle_id=f"draft-{tag}", version=f"draft-{tag}-1", status="pending", manifest_uri=f"test://{tag}"
            )
        )
        tx.flush()
        tx.add(
            ClinicalRule(
                rule_id=f"urg.{tag}.ache",
                bundle_id=f"draft-{tag}",
                rule_type="urgency",
                applicability={},
                condition_ast={"op": "and", "args": [{"op": "present", "feature": f"feat_{tag}_ruled"}]},
                action={"type": "escalate", "urgency": "urgent", "text": "Sample text (invented)."},
                evidence_ids=["src.sample"],
                priority=10,
                status="pending",
            )
        )
    return tag


def _history(client, who: Api, feature_id: str):
    return client.get(f"/internal/v1/review/features/{feature_id}/history", headers=who.headers(None))


def _merge(client, who: Api, source: str, target: str):
    body = {"source_feature_id": source, "target_feature_id": target, "note": "Two names for one thing."}
    return client.post(MERGE, headers=who.headers(None), json=body)


def test_a_merge_keeps_one_item_makes_the_other_another_name_of_it_and_is_recorded(
    client, api: Api, reviewer: Api, items, owner_db
):
    kept, alias, old, number, ruled = (f"feat_{items}_{key}" for key in ("kept", "alias", "old", "number", "ruled"))
    assert _merge(client, api, alias, kept).status_code == 403 and _history(client, api, kept).status_code == 403
    assert _merge(client, reviewer, kept, kept).status_code == 422
    assert _merge(client, reviewer, f"feat_{items}_none", kept).status_code == 404
    # A yes-or-no item and a number are not one item, whatever they are called.
    refused = _merge(client, reviewer, number, kept)
    assert (refused.status_code, refused.json()["code"]) == (409, "not_the_same_kind_of_value")
    # An item a rule names is not merged away; the other name is merged into it.
    refused = _merge(client, reviewer, ruled, kept)
    assert (refused.status_code, refused.json()["code"]) == (409, "item_named_by_a_rule")
    assert f"urg.{items}.ache" in refused.json()["message"] and "merge" in refused.json()["message"]

    merged = _merge(client, reviewer, alias, kept)
    assert merged.status_code == 200
    body = merged.json()
    assert body["kept"] == {"feature_id": kept, "preferred_name": f"pretend ache {items}", "review_status": "pending"}
    # Its own other names first, then the merged name and that name's other names.
    assert body["other_names"] == ["made-up ache", f"pretend-ache {items}", "ache (pretended)"]
    assert body["merged_items"] == [{"feature_id": alias, "preferred_name": f"pretend-ache {items}"}]
    with owner_db.transaction(None, role="migration") as tx:
        row = tx.get(Feature, alias)
        # The merged name stays, with its own name, pointing at the kept item.
        assert (row.redirected_to, row.status, row.preferred_name) == (kept, "retired", f"pretend-ache {items}")
    event = body["history"][0]
    assert (event["action"], event["feature_id"], event["other_id"], event["reviewer"], event["note"]) == (
        "merge",
        alias,
        kept,
        f"dev-reviewer:{reviewer.subject}",
        "Two names for one thing.",
    )
    assert event["detail"]["status_before"] == "pending"
    assert (
        _merge(client, reviewer, alias, old).json()["code"],
        _merge(client, reviewer, old, alias).json()["code"],
    ) == (
        "already_merged",
        "target_is_merged",
    )
    assert _history(client, reviewer, alias).json()["kept"]["feature_id"] == kept
    # A merged name takes no decision of its own, and the list of items says where it went.
    decided = client.post(
        DECIDE,
        headers=reviewer.headers(None),
        json={"target_type": "feature", "target_id": alias, "note": "Looks right.", "status": "approved"},
    )
    assert (decided.status_code, decided.json()["code"]) == (409, "feature_is_merged")
    listed = client.get(f"/internal/v1/review/features?q={items}", headers=reviewer.headers(None)).json()["items"]
    assert {row["feature_id"]: row["merged_into"] for row in listed}[alias] == kept
    # The rule's item can be the one kept: a name merged into it leaves the rule as it is.
    assert _merge(client, reviewer, old, ruled).status_code == 200
    assert _history(client, reviewer, ruled).json()["named_by"] == [f"urg.{items}.ache"]


def test_a_split_takes_a_merged_name_out_again_and_the_history_keeps_both_events(
    client, reviewer: Api, items, owner_db
):
    kept, alias = f"feat_{items}_kept", f"feat_{items}_alias"
    with owner_db.transaction(None, role="migration") as tx:
        tx.get(Feature, alias).status = "approved"
    assert _merge(client, reviewer, alias, kept).status_code == 200
    body = {"feature_id": alias, "note": "They are not the same after all."}
    out = client.post(SPLIT, headers=reviewer.headers(None), json=body)
    assert out.status_code == 200
    assert [event["action"] for event in out.json()["history"]] == ["merge", "split"]
    assert out.json()["merged_items"] == [] and out.json()["other_names"] == ["made-up ache"]
    with owner_db.transaction(None, role="migration") as tx:
        row = tx.get(Feature, alias)
        assert (row.redirected_to, row.status) == (None, "approved")  # it gets back the status it had
    assert client.post(SPLIT, headers=reviewer.headers(None), json=body).json()["code"] == "not_merged"


def test_a_published_list_and_a_knowledge_version_read_a_merged_name_through_the_kept_item(
    client, reviewer: Api, items, owner_db, monkeypatch
):
    tag, kept, alias = items, f"feat_{items}_kept", f"feat_{items}_alias"
    with owner_db.transaction(None, role="migration") as tx:
        tx.add(MappingRelease(release_id=f"map-{tag}", version=f"map-{tag}-0"))
        tx.add(
            Source(
                source_id=f"src_{tag}",
                source_name=f"sample-{tag}.csv",
                version="1",
                origin_url="https://example.org/sample",
                licence="Sample licence 1.0",
                sha256=f"sha-{tag}",
                provenance_status="approved",
            )
        )
        tx.add(Disease(disease_id=f"dis_{tag}", preferred_name=f"pretend illness {tag}", status="approved"))
        tx.flush()
        tx.add(
            KnowledgeRelease(
                release_id=f"know-{tag}",
                mapping_release_id=f"map-{tag}",
                version=f"know-{tag}-0",
                manifest_uri=f"test://know-{tag}",
            )
        )
        tx.add(
            SourceRecord(
                record_id=f"rec_{tag}",
                source_id=f"src_{tag}",
                file_path="sample.csv",
                row_number=1,
                content_hash=f"hash-{tag}",
                raw_object_uri=f"test://{tag}/1",
            )
        )
        # The column and the fact were given the name that is merged away below.
        tx.add(
            FeatureMapping(
                mapping_id=f"fm_{tag}",
                release_id=f"map-{tag}",
                source_id=f"src_{tag}",
                file_path="sample.csv",
                column_index=3,
                original_term="PRETEND-ACHE",
                feature_id=alias,
                zero_semantics="not_recorded",
                transformation={},
                status="approved",
            )
        )
        tx.flush()
        tx.add(
            DiseaseFeatureEvidence(
                evidence_id=f"ev_{tag}",
                disease_id=f"dis_{tag}",
                feature_id=alias,
                record_id=f"rec_{tag}",
                relationship="sample_relation",
                context={},
                evidence_type="sample_kind_of_fact",
            )
        )
        tx.get(Feature, kept).status = "approved"
        tx.get(Feature, alias).status = "approved"
    # The fact is approved by a reviewer, through the review path: a fact approved by nobody is a fault that the
    # loaders' own checks report for the whole table, whatever kind the fact is of (BUG-033).
    approved = client.post(
        DECIDE,
        headers=reviewer.headers(None),
        json={"target_type": "evidence", "target_id": f"ev_{tag}", "note": "A sample fact.", "status": "approved"},
    )
    assert approved.status_code == 200
    assert _merge(client, reviewer, alias, kept).status_code == 200

    with owner_db.transaction(None, role="migration") as tx:
        content, _problems = published_mappings._content(tx, tx.get(MappingRelease, f"map-{tag}"))
        listed = [entry for entry in content["features"] if tag in entry["feature_id"]]
        # The merged name is not an item of its own: the kept item carries it as another name.
        assert [(entry["feature_id"], entry["aliases"], entry["merged_items"]) for entry in listed] == [
            (kept, ["made-up ache", f"pretend-ache {tag}", "ache (pretended)"], [alias])
        ]
        assert {key: value for key, value in content["feature_redirects"].items() if tag in key} == {alias: kept}
        columns = [entry for entry in content["feature_mappings"] if entry["mapping_id"] == f"fm_{tag}"]
        assert [(entry["feature_id"], entry["named_feature_id"]) for entry in columns] == [(kept, alias)]

        # A knowledge version reads the list of names in use; here that is the content just built.
        pinned = SimpleNamespace(content=content, working_id=f"map-{tag}", release_id=f"map-{tag}.r1", sha256="x")
        monkeypatch.setattr(published_knowledge.publishing, "current", lambda _tx, _model: pinned)
        knowledge, _problems = published_knowledge._content(
            tx, tx.get(KnowledgeRelease, f"know-{tag}"), datetime.now(UTC)
        )
        facts = [entry for entry in knowledge["evidence"] if entry["evidence_id"] == f"ev_{tag}"]
        assert [(entry["feature_id"], entry["named_feature_id"], entry["resolves_to"]) for entry in facts] == [
            (kept, alias, f"dis_{tag}")
        ]


def test_the_database_keeps_the_history_unchanged_and_lets_only_a_reviewer_merge(
    client, reviewer: Api, items, owner_db, db
):
    if owner_db.engine.dialect.name != "postgresql":
        pytest.skip("row-level security and the append-only trigger exist only on PostgreSQL")
    kept, alias = f"feat_{items}_kept", f"feat_{items}_alias"
    assert _merge(client, reviewer, alias, kept).status_code == 200
    # The loaders' own check reads a merged name as reviewed, not as changed by nobody: the merge is on record.
    from feeltriva_ingestion.decisions import standing

    with owner_db.transaction(None, role="migration") as tx:
        found = tx.execute(
            text(f"SELECT feature_id, {standing('features')} FROM features WHERE feature_id IN (:a, :b)"),
            {"a": alias, "b": kept},
        ).all()
        assert dict(found) == {alias: "reviewed", kept: "pending"}
    with pytest.raises(DBAPIError, match="cannot be changed"), owner_db.transaction(None, role="migration") as tx:
        tx.execute(text("UPDATE feature_history SET note = 'rewritten' WHERE feature_id = :id"), {"id": alias})
    with pytest.raises(DBAPIError, match="cannot be changed"), owner_db.transaction(None, role="migration") as tx:
        tx.execute(text("DELETE FROM feature_history WHERE feature_id = :id"), {"id": alias})
    # Outside a reviewer's transaction the application role changes nothing: the row is not visible to the update.
    with db.transaction("dev:someone") as tx:
        changed = tx.execute(
            text("UPDATE features SET redirected_to = NULL WHERE feature_id = :id"), {"id": alias}
        ).rowcount
        assert changed == 0
    with pytest.raises(DBAPIError), db.transaction("dev:someone") as tx:
        tx.execute(
            text(
                "INSERT INTO feature_history (event_id, action, feature_id, other_id, reviewer, note) "
                "VALUES (gen_random_uuid(), 'merge', :a, :b, 'nobody', 'x')"
            ),
            {"a": alias, "b": kept},
        )


WHO = Principal(subject="dev-reviewer:itemdedupe", roles=frozenset({"reviewer"}))


def test_item_names_are_grouped_by_rule_and_a_pair_sharing_only_a_code_is_never_merged(owner_db, container):
    tag = uuid.uuid4().hex[:8]
    names = {
        "eye": (f"pain in pretend eye {tag}", "boolean"),
        "eye2": (f"pretend eye pain {tag}", "boolean"),
        "eye3": (f"pain in pretend-eye {tag}", "boolean"),  # the same words as the first with other punctuation
        "head": (f"pretend regurgitation {tag}", "boolean"),
        "head1": (f"pretend regurgitation {tag}.1", "boolean"),  # a repeated column heading
        "mass": (f"pretend bladder mass {tag}", "boolean"),
        "mass2": (f"pretend kidney mass {tag}", "boolean"),
        "count": (f"pretend count {tag}", "number"),
        "count2": (f"pretend-count {tag}", "boolean"),
        "ruled": (f"pretend ruled {tag}", "boolean"),
        "ruled2": (f"pretend-ruled {tag}", "boolean"),
    }
    with owner_db.transaction(None, role="migration") as tx:
        for key, (name, value_type) in names.items():
            tx.add(Feature(feature_id=f"feat_{tag}_{key}", preferred_name=name, kind="symptom", value_type=value_type))
        tx.add(
            RuleBundle(
                bundle_id=f"draft-{tag}", version=f"draft-{tag}-1", status="pending", manifest_uri=f"test://{tag}"
            )
        )
        tx.flush()
        tx.add(
            ClinicalRule(
                rule_id=f"urg.{tag}.ruled",
                bundle_id=f"draft-{tag}",
                rule_type="urgency",
                applicability={},
                condition_ast={"op": "present", "feature": f"feat_{tag}_ruled2"},
                action={"type": "escalate", "urgency": "urgent", "text": "Sample text (invented)."},
                evidence_ids=["src.sample"],
                priority=10,
                status="approved",
            )
        )

        def pair(key, left, right, signals, status="pending"):
            tx.add(
                RelationSuggestion(
                    suggestion_id=f"rs_{tag}_{key}",
                    subject_type="feature",
                    relation="possible_synonym",
                    left_id=f"feat_{tag}_{left}",
                    right_id=f"feat_{tag}_{right}",
                    left_label=names[left][0],
                    right_label=names[right][0],
                    signals=signals,
                    status=status,
                )
            )

        code = {"signal": "same_standard_code", "vocabulary": "ICD-11 MMS", "code": "X1", "release": "t"}
        pair("eye", "eye", "eye2", [{"signal": "same_words_other_order_or_number"}])
        pair("mass", "mass", "mass2", [code])  # one code that covers two different things
    with owner_db.transaction(None, role="migration") as tx:
        found = item_duplicates.item_groups(tx)
        groups = {group["kept_name"]: group for group in found["groups"] if tag in group["kept_name"]}
        left = [entry for entry in found["left_for_a_person"] if tag in " ".join(entry["names"])]
    short = {key: f"feat_{tag}_{key}" for key in names}
    assert {name: (group["merged"], group["repeated_heading"]) for name, group in groups.items()} == {
        # The shortest of three names that no data file and no rule tells apart.
        names["eye2"][0]: ([short["eye"], short["eye3"]], False),
        names["head"][0]: ([short["head1"]], True),
        # The name a rule names is the one kept, whatever its spelling.
        names["ruled2"][0]: ([short["ruled"]], False),
    }
    assert groups[names["eye2"][0]]["suggestions"] == [f"rs_{tag}_eye"]
    assert left == [
        {
            "names": sorted([names["count"][0], names["count2"][0]]),
            "reason": "these names do not hold the same kind of value",
        }
    ]
    mine = [group for group in groups.values() if not group["repeated_heading"]]
    done = item_duplicates.merge_item_groups(container.db, WHO, mine, "Two names for one item (test).")
    assert (done["groups"], done["names_merged"], done["merges_refused"], done["suggestions_approved"]) == (2, 3, [], 1)
    with owner_db.transaction(None, role="migration") as tx:
        assert tx.get(Feature, short["eye"]).redirected_to == short["eye2"]
        assert (
            tx.get(Feature, short["mass"]).redirected_to is None
            and tx.get(Feature, short["head1"]).redirected_to is None
        )
        assert tx.get(RelationSuggestion, f"rs_{tag}_mass").status == "pending"
        again = [group for group in item_duplicates.item_groups(tx)["groups"] if tag in group["kept_name"]]
        assert [group["kept_name"] for group in again] == [names["head"][0]]  # nothing is merged twice
