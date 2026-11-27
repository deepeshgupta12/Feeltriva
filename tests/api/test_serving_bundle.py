"""The stored response texts and the serving bundle assembled from the current releases (M2.5f). Invented rules."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest
from feeltriva_api import published_mappings, releases, response_text_sets, review_rules, serving_bundle
from feeltriva_api.auth import Principal
from feeltriva_api.db import Database
from feeltriva_api.errors import ApiError
from feeltriva_api.models import (
    Base,
    ClinicalRule,
    Feature,
    KnowledgeRelease,
    MappingRelease,
    PublishedKnowledge,
    ResponseTextSet,
    RuleBundle,
)
from feeltriva_api.releases import verify_published
from feeltriva_api.review import ReviewService
from feeltriva_api.seed import seed_release
from feeltriva_clinical import BundleError, load_bundle, load_fixture_bundle, validate_bundle
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from tests.conftest import Api

WHO = Principal(subject="dev-reviewer:someone", roles=frozenset({"reviewer"}))
USER = Principal(subject="dev:user")
NAMES = ("hat", "scarf", "coat")


def _decide(db: Database, target_type: str, target_id: str, status: str = "approved") -> None:
    ReviewService(db).record_review(WHO, target_type=target_type, target_id=target_id, note="Decided.", status=status)


@pytest.fixture
def world(monkeypatch):
    """A database of its own with an invented rule bundle of two rules, three features and a mapping working set.
    Nothing is decided or published."""
    db = Database("sqlite://")
    Base.metadata.create_all(db.engine)
    with db.transaction(None, role="migration") as tx:
        tx.add(MappingRelease(release_id="map-own", version="map-own-0"))
        tx.add(RuleBundle(bundle_id="rules-own", version="rules-own-1", manifest_uri="draft://rules-own/1#sha256=fp"))
        for name in NAMES:
            tx.add(Feature(feature_id=f"feat_{name}", preferred_name=name, kind="symptom", value_type="boolean"))
        tx.flush()
        for name, level, priority in (("hat", "emergency", 10), ("scarf", "urgent", 100)):
            tx.add(
                ClinicalRule(
                    rule_id=f"urg.{name}",
                    bundle_id="rules-own",
                    rule_type="urgency",
                    applicability={},
                    condition_ast={"op": "present", "feature": f"feat_{name}"},
                    action={"type": "escalate", "urgency": level, "text": f"Sample text for {name} (invented)."},
                    evidence_ids=["src.sample"],
                    priority=priority,
                )
            )
    source = SimpleNamespace(
        evidence_id="src.sample",
        publisher="Sample publisher",
        source_title="Sample page",
        source_url="https://example.org/sample",
        page_reviewed="",
        licence="none",
        quotes=["A sample sentence."],
    )
    draft = SimpleNamespace(
        sources=[source],
        features=[SimpleNamespace(feature_id=f"feat_{name}", name=name, question=None) for name in NAMES],
        numbers=[],
    )
    monkeypatch.setattr(review_rules, "_rule_file", lambda bundle_id: (draft, "fp"))
    return db


def _publish_rules(db: Database) -> None:
    for name in ("hat", "scarf"):
        _decide(db, "clinical_rule", f"urg.{name}")
    _decide(db, "rule_bundle", "rules-own")
    releases.publish(db, WHO, bundle_id="rules-own", note="Publish.")


def _publish_features(db: Database, *names: str) -> str:
    for name in names:
        _decide(db, "feature", f"feat_{name}")
    return published_mappings.publish(db, WHO, mapping_release_id="map-own", note="Publish.")["release_id"]


def _approve_texts(db: Database) -> None:
    draft, digest = response_text_sets.texts_file()
    response_text_sets.store_texts(db, draft, digest)
    _decide(db, "response_texts", draft.draft_id)


def test_the_serving_bundle_is_assembled_only_when_every_part_is_published_or_approved(world, tmp_path):
    db = world
    # Nothing published, nothing approved: every missing part is named, and nothing is written.
    bundle, described = serving_bundle.assemble(db)
    assert bundle is None and described["assembled"] is False
    assert described["problems"] == [
        "no rule release is current",
        "no mapping release is current",
        "the response texts are not approved",
    ]
    refused = serving_bundle.write(db, tmp_path / "bundle.json")
    assert refused["assembled"] is False and not (tmp_path / "bundle.json").exists()
    _publish_rules(db)
    assert serving_bundle.assemble(db)[1]["problems"] == [
        "no mapping release is current",
        "the response texts are not approved",
    ]
    # A mapping release that does not hold a feature a rule names: the feature is named.
    _publish_features(db, "hat")
    _approve_texts(db)
    assert serving_bundle.assemble(db)[1]["problems"] == [
        "1 features the rules or questions name are not in the current mapping release map-own.r1: feat_scarf"
    ]
    current = _publish_features(db, "scarf")
    bundle, described = serving_bundle.assemble(db)
    assert bundle is not None and described["problems"] == []
    assert (described["rules"], described["features"], described["response_texts"], described["candidates"]) == (
        2,
        2,
        4,
        0,
    )
    assert described["built_from"]["mapping_release"]["release_id"] == current == "map-own.r2"
    assert described["built_from"]["response_texts"]["by"] == "dev-reviewer:someone"
    # What it holds: the rules of the current rule release, the features of the mapping release, the approved texts.
    assert (bundle.bundle_id, bundle.rules_version, bundle.synthetic, bundle.status) == (
        "rules-own",
        "rules-own.r1",
        False,
        "approved",
    )
    assert [(rule.rule_id, rule.action.urgency, rule.status) for rule in bundle.rules] == [
        ("urg.hat", "emergency", "approved"),
        ("urg.scarf", "urgent", "approved"),
    ]
    assert [(feature.feature_id, feature.status) for feature in bundle.features] == [
        ("feat_hat", "approved"),
        ("feat_scarf", "approved"),
    ]
    assert bundle.templates == response_text_sets.texts_file()[0].as_templates()
    # No knowledge release is current: the bundle names none and carries no candidates and no citations.
    assert (bundle.knowledge_release_id, bundle.knowledge_version, bundle.candidates, bundle.evidence) == (
        None,
        None,
        [],
        [],
    )
    # It passes the clinical-mode checks and its rules are the current release.
    validate_bundle(bundle, clinical_mode=True)
    verify_published(db, bundle)
    serving_bundle.verify_serving(db, bundle)
    # Written to a file, it is what clinical mode loads; a second file says what it was built from.
    written = serving_bundle.write(db, tmp_path / "bundle.json")
    assert load_bundle(tmp_path / "bundle.json", clinical_mode=True) == bundle
    manifest = json.loads((tmp_path / "bundle.manifest.json").read_text())
    assert manifest["sha256"] == written["sha256"] and manifest["built_from"]["rule_release"]["release_id"] == (
        "rules-own.r1"
    )
    # Registering the bundle's reference rows registers no knowledge release, because it names none.
    seed_release(db, bundle)
    with db.transaction(None) as tx:
        assert tx.scalar(select(func.count()).select_from(KnowledgeRelease)) == 0
    with pytest.raises(ApiError) as forbidden:
        serving_bundle.preview(db, USER)
    assert forbidden.value.status == 403 and serving_bundle.preview(db, WHO)["assembled"] is True


def test_a_loaded_bundle_that_is_not_what_the_current_releases_give_is_refused(world):
    db = world
    _publish_rules(db)
    _publish_features(db, "hat", "scarf")
    _approve_texts(db)
    bundle, _ = serving_bundle.assemble(db)
    assert bundle is not None
    serving_bundle.verify_serving(db, bundle)
    # A response text nobody approved.
    edited = bundle.model_copy(
        update={
            "templates": bundle.templates.model_copy(update={"confirm_details": "Other words, approved by nobody."})
        }
    )
    with pytest.raises(RuntimeError, match="differs in: templates"):
        serving_bundle.verify_serving(db, edited)
    # The fixture bundle is not a serving bundle.
    with pytest.raises(RuntimeError, match="differs in: "):
        serving_bundle.verify_serving(db, load_fixture_bundle())
    # A bundle assembled before a release changed is stale: a later mapping release holds one more feature.
    _publish_features(db, "coat")
    with pytest.raises(RuntimeError, match="differs in: features"):
        serving_bundle.verify_serving(db, bundle)
    # When the approval of the texts is withdrawn, nothing can be served.
    _decide(db, "response_texts", "response-texts-draft", "pending")
    with pytest.raises(RuntimeError, match="missing: the response texts are not approved"):
        serving_bundle.verify_serving(db, bundle)


def test_a_knowledge_release_must_be_pinned_to_the_current_mapping_release(world):
    db = world
    _publish_rules(db)
    first = _publish_features(db, "hat", "scarf")
    _approve_texts(db)
    with db.transaction(None, role="migration") as tx:
        tx.add(KnowledgeRelease(release_id="know-own", version="know-own-0", manifest_uri="test://know-own"))
        tx.flush()
        tx.add(
            PublishedKnowledge(
                release_id="know-own.r1",
                working_id="know-own",
                mapping_release=first,
                number=1,
                content={"statements": [], "evidence": []},
                sha256="sample",
                published_by="dev-reviewer:someone",
                is_current=True,
            )
        )
    # Pinned to the current mapping release: the bundle names the knowledge release.
    bundle, described = serving_bundle.assemble(db)
    assert bundle is not None and (bundle.knowledge_release_id, bundle.knowledge_version) == ("know-own", "know-own.r1")
    assert described["built_from"]["knowledge_release"]["mapping_release"] == first
    # A later mapping release becomes current: the knowledge release was published against the earlier one.
    second = _publish_features(db, "coat")
    bundle, described = serving_bundle.assemble(db)
    assert bundle is None and described["problems"] == [
        f"the current knowledge release know-own.r1 is pinned to the mapping release {first}, "
        f"which is not the current one ({second})"
    ]


def test_a_bundle_names_a_knowledge_release_fully_or_not_at_all():
    fixture = load_fixture_bundle()
    none = {"knowledge_release_id": None, "knowledge_version": None}
    # The fixture has candidates and citations: they need a knowledge release.
    with pytest.raises(BundleError, match="candidates and evidence need a knowledge release"):
        validate_bundle(fixture.model_copy(update=none), clinical_mode=False)
    validate_bundle(fixture.model_copy(update={**none, "candidates": [], "evidence": []}), clinical_mode=False)
    with pytest.raises(BundleError, match="or not at all"):
        validate_bundle(fixture.model_copy(update={"knowledge_version": None}), clinical_mode=False)


def test_the_response_texts_are_stored_as_the_file_has_them_and_approved_only_as_stored(world, monkeypatch):
    db = world
    draft, digest = response_text_sets.texts_file()
    stored = response_text_sets.store_texts(db, draft, digest)
    assert (stored["outcome"], stored["stored_status"], stored["set_id"]) == ("stored", "pending", draft.draft_id)
    assert response_text_sets.store_texts(db, draft, digest)["outcome"] == "unchanged"
    listed = response_text_sets.list_sets(db, WHO)["items"]
    assert [(item["set_id"], item["review_status"], item["approved_by"]) for item in listed] == [
        (draft.draft_id, "pending", None)
    ]
    assert listed[0]["texts"] == draft.as_templates().model_dump() and sorted(listed[0]["texts"]) == [
        "confirm_details",
        "insufficient_information",
        "provisional_next_step",
        "system_unavailable",
    ]
    with pytest.raises(ApiError) as forbidden:
        response_text_sets.list_sets(db, USER)
    assert forbidden.value.status == 403
    # The file on this installation is no longer the one stored: the approval is refused.
    monkeypatch.setattr(response_text_sets, "texts_file", lambda: (draft, "another-fingerprint"))
    with pytest.raises(ApiError) as changed:
        _decide(db, "response_texts", draft.draft_id)
    assert (changed.value.status, changed.value.code) == (409, "texts_file_changed")
    monkeypatch.undo()
    _decide(db, "response_texts", draft.draft_id)
    with db.transaction(None) as tx:
        row = tx.get(ResponseTextSet, draft.draft_id)
        assert (row.status, row.approved_by, row.fingerprint) == ("approved", "dev-reviewer:someone", digest)
        assert row.approved_at is not None
    # A decided set is not rewritten by storing a changed file.
    kept = response_text_sets.store_texts(db, draft, "a-changed-file")
    assert kept["outcome"].startswith("kept: a reviewer has decided") and kept["stored_is_this_file"] is False
    # Withdrawing the approval names nobody.
    _decide(db, "response_texts", draft.draft_id, "pending")
    with db.transaction(None) as tx:
        row = tx.get(ResponseTextSet, draft.draft_id)
        assert (row.status, row.approved_by, row.approved_at) == ("pending", None, None)


def test_the_routes_for_the_texts_and_the_serving_bundle_are_for_reviewers_only(client, api: Api):
    reviewer = Api(client, subject="rev", token=f"dev-reviewer:rev-{uuid.uuid4().hex[:8]}")
    for path in ("/internal/v1/review/response-texts", "/internal/v1/review/serving-bundle"):
        assert client.get(path, headers=api.headers(None)).status_code == 403
        assert client.get(path, headers=reviewer.headers(None)).status_code == 200
    preview = client.get("/internal/v1/review/serving-bundle", headers=reviewer.headers(None)).json()
    assert set(preview) >= {"assembled", "problems", "built_from"}
    assert set(preview["built_from"]) == {"rule_release", "mapping_release", "response_texts", "knowledge_release"}


@pytest.mark.postgres
def test_the_database_lets_nobody_change_the_texts_of_a_decided_set(db, owner_db):
    tag = uuid.uuid4().hex[:10]
    one = {"s": f"texts-{tag}"}
    with owner_db.transaction(None, role="migration") as tx:
        tx.add(
            ResponseTextSet(
                set_id=f"texts-{tag}", version=f"texts-{tag}-1", fingerprint="fp", texts={"sample": "Words."}
            )
        )
    # Pending, the owner of the schema may still store changed texts.
    with owner_db.transaction(None, role="migration") as tx:
        tx.execute(
            text("""UPDATE response_text_sets SET texts = '{"sample": "Other."}'::jsonb WHERE set_id = :s"""), one
        )
    # The application role decides a set only in a reviewer's transaction, and can never change a text.
    with db.transaction("someone") as tx:
        decided = tx.execute(text("UPDATE response_text_sets SET status = 'approved' WHERE set_id = :s"), one)
        assert decided.rowcount == 0
    with pytest.raises(DBAPIError), db.transaction("someone", role="reviewer") as tx:
        tx.execute(text("""UPDATE response_text_sets SET texts = '{}'::jsonb WHERE set_id = :s"""), one)
    with db.transaction("someone", role="reviewer") as tx:
        decided = tx.execute(text("UPDATE response_text_sets SET status = 'approved' WHERE set_id = :s"), one)
        assert decided.rowcount == 1
    # Decided: even the owner of the schema cannot change the words.
    for statement in (
        """UPDATE response_text_sets SET texts = '{"sample": "Changed."}'::jsonb WHERE set_id = :s""",
        "UPDATE response_text_sets SET fingerprint = 'x' WHERE set_id = :s",
    ):
        with pytest.raises(DBAPIError, match="cannot be changed"), owner_db.transaction(None, role="migration") as tx:
            tx.execute(text(statement), one)


def test_a_question_keeps_what_the_reviewer_gave_it_on_the_way_to_a_published_rule_set(owner_db):
    # BUG-036: which option means "not present", the reviewer's order and the mark "essential" were dropped
    # between the rule file and a published rule set, so "None of these" would have been read as present.
    import uuid

    from feeltriva_api import releases
    from feeltriva_api.models import ClinicalRule, Feature, FollowupQuestion, RuleBundle
    from feeltriva_api.serving_bundle import question_of

    with owner_db.transaction(None, role="migration") as tx:
        # The synthetic rule set is stored by the test setup, through the same function as on any installation.
        stored = tx.get(FollowupQuestion, "fx.q.gamma").branch_rules
        assert stored == {
            "option_presence": {"none": "absent"},
            "priority": 20,
            "essential": False,
            "stores": "observation",
        }

        tag = uuid.uuid4().hex[:8]
        tx.add(
            Feature(
                feature_id=f"feat_{tag}", preferred_name=f"pretend sign {tag}", kind="symptom", value_type="boolean"
            )
        )
        tx.add(RuleBundle(bundle_id=f"qp-{tag}", version=f"qp-{tag}-1", status="pending", manifest_uri=f"test://{tag}"))
        tx.flush()
        schema = {
            "type": "single_choice",
            "options": [{"value": "a", "label": "A"}, {"value": "none", "label": "None"}],
        }
        for key, more in (
            ("kept", {"option_presence": {"none": "absent"}, "priority": 7, "essential": True}),
            ("old", {}),
        ):
            tx.add(
                FollowupQuestion(
                    question_id=f"q.{tag}.{key}",
                    bundle_id=f"qp-{tag}",
                    feature_id=f"feat_{tag}",
                    wording="An invented question?",
                    answer_schema=schema,
                    applicability={},
                    branch_rules=more,
                    evidence_ids=[],
                    status="approved",
                )
            )
        tx.add(
            ClinicalRule(
                rule_id=f"urg.{tag}",
                bundle_id=f"qp-{tag}",
                rule_type="urgency",
                applicability={},
                condition_ast={"op": "present", "feature": f"feat_{tag}"},
                action={"type": "escalate", "urgency": "urgent", "text": "Sample text (invented)."},
                evidence_ids=[],
                priority=10,
                status="approved",
            )
        )
        tx.flush()
        content, _problems = releases._content(tx, tx.get(RuleBundle, f"qp-{tag}"))
        published = {entry["question_id"].rsplit(".", 1)[1]: entry for entry in content["questions"]}
        assert (
            published["kept"]["option_presence"],
            published["kept"]["priority"],
            published["kept"]["essential"],
        ) == (
            {"none": "absent"},
            7,
            True,
        )
        # A question stored before the fix has none of the three: it is published as it always was.
        assert (published["old"]["option_presence"], published["old"]["priority"], published["old"]["essential"]) == (
            {},
            100,
            False,
        )
        asked = question_of(published["kept"])
        assert (asked.option_presence, asked.priority, asked.essential, asked.status) == (
            {"none": "absent"},
            7,
            True,
            "approved",
        )
        # A rule set published before the fix holds none of the keys and is read as before.
        bare = {k: v for k, v in published["kept"].items() if k not in ("option_presence", "priority", "essential")}
        before = question_of(bare)
        assert (before.option_presence, before.priority, before.essential) == ({}, 100, False)
        tx.rollback()  # nothing of this test stays in the database
