"""Internal review workspace and reviewed-only serving."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from feeltriva_api.models import (
    AuditEvent,
    Disease,
    DiseaseMapping,
    FeatureMapping,
    MappingRelease,
    ReviewNote,
    Source,
    SourceRecord,
    Statement,
    StatementSource,
)
from sqlalchemy import select, text

from tests.conftest import Api


@pytest.fixture
def reviewer(client) -> Api:
    name = f"rev-{uuid.uuid4().hex[:8]}"
    return Api(client, subject=name, token=f"dev-reviewer:{name}")


@pytest.fixture
def seeded(owner_db):
    """A small synthetic review set with unique IDs (the PostgreSQL test database persists)."""
    tag = uuid.uuid4().hex[:8]
    ids = {
        k: f"t_{k}_{tag}"
        for k in (
            "src",
            "rel",
            "dis",
            "dis_old",
            "dm",
            "fm_a",
            "fm_b",
            "rec",
            "st_ok",
            "st_pending",
            "st_nosrc",
            "st_expired",
        )
    }
    with owner_db.transaction(None) as tx:
        tx.add(Source(source_id=ids["src"], source_name=f"synthetic-{tag}", version="1", sha256="0" * 64))
        tx.add(MappingRelease(release_id=ids["rel"], version=f"test-{tag}"))
        tx.flush()
        tx.add(Disease(disease_id=ids["dis"], preferred_name=f"Synthetic condition {tag}", status="pending"))
        tx.flush()
        tx.add(
            Disease(
                disease_id=ids["dis_old"], preferred_name=f"Old alias {tag}", status="retired", redirected_to=ids["dis"]
            )
        )
        tx.add(
            SourceRecord(
                record_id=ids["rec"],
                source_id=ids["src"],
                file_path="f.csv",
                row_number=1,
                content_hash="h",
                raw_object_uri="zip://synthetic",
            )
        )
        tx.flush()
        tx.add(
            DiseaseMapping(
                mapping_id=ids["dm"],
                release_id=ids["rel"],
                source_id=ids["src"],
                original_label=f"Synthetic  Condition {tag}",
                disease_id=ids["dis"],
                method="lexical",
            )
        )
        for key, column in (("fm_a", 3), ("fm_b", 9)):
            tx.add(
                FeatureMapping(
                    mapping_id=ids[key],
                    release_id=ids["rel"],
                    source_id=ids["src"],
                    file_path="f.csv",
                    column_index=column,
                    original_term=f"dup_{tag}",
                    transformation={"repeated_header": True, "repeated_positions": [3, 9], "disagreement_rows": 12},
                )
            )
        past = datetime.now(UTC) - timedelta(days=1)
        for key, status, expires in (
            ("st_ok", "pending", None),
            ("st_pending", "pending", None),
            ("st_nosrc", "approved", None),
            ("st_expired", "approved", past),
        ):
            tx.add(
                Statement(
                    statement_id=ids[key],
                    disease_id=ids["dis"],
                    statement_type="description",
                    text_content=f"Synthetic statement {key}",
                    status=status,
                    expires_at=expires,
                )
            )
        tx.flush()
        for key in ("st_ok", "st_pending", "st_expired"):
            tx.add(StatementSource(statement_id=ids[key], record_id=ids["rec"], source_url="https://example.org/s"))
    return ids


def _approve(owner_db, model, key):
    with owner_db.transaction(None) as tx:
        tx.get(model, key).status = "approved"


# ---- access ---------------------------------------------------------------------------
def test_review_routes_require_the_reviewer_role(client, api: Api, seeded):
    paths = ["overview", "disease-mappings", "feature-mappings", "statements"]
    for path in paths:
        assert client.get(f"/internal/v1/review/{path}").status_code == 401
        r = client.get(f"/internal/v1/review/{path}", headers=api.headers(None))
        assert r.status_code == 403 and r.json()["code"] == "forbidden"
    r = client.post(
        "/internal/v1/review/decisions",
        headers=api.headers(None),
        json={"target_type": "disease_mapping", "target_id": seeded["dm"], "note": "x", "status": "approved"},
    )
    assert r.status_code == 403


def test_reviewer_can_browse_mappings_with_source_term_position_and_conflicts(client, reviewer: Api, seeded):
    headers = reviewer.headers(None)
    tag = seeded["dm"].rsplit("_", 1)[1]
    assert (
        client.get("/internal/v1/review/overview", headers=headers).json()["label"].startswith("Imported dataset audit")
    )
    found = client.get(
        "/internal/v1/review/disease-mappings", params={"q": tag, "status": "pending"}, headers=headers
    ).json()
    assert found["total"] == 1
    item = found["items"][0]
    assert item["original_term"] == f"Synthetic  Condition {tag}"  # original spelling preserved
    assert (item["proposed_canonical_id"], item["mapping_method"], item["review_status"]) == (
        seeded["dis"],
        "lexical",
        "pending",
    )
    conflicts = client.get(
        "/internal/v1/review/feature-mappings", params={"q": f"dup_{tag}", "conflicts_only": True}, headers=headers
    ).json()
    assert [i["column_index"] for i in conflicts["items"]] == [3, 9]  # both positions kept
    assert all(i["conflicts"]["disagreement_rows"] == 12 for i in conflicts["items"])
    statements = client.get(
        "/internal/v1/review/statements", params={"disease_id": seeded["dis"]}, headers=headers
    ).json()
    assert statements["total"] == 4
    sourced = {s["statement_id"]: s["sources"] for s in statements["items"]}
    assert sourced[seeded["st_ok"]][0]["source_url"] == "https://example.org/s" and sourced[seeded["st_nosrc"]] == []


def test_review_decision_is_attributed_noted_and_audited(client, reviewer: Api, seeded, owner_db):
    headers = reviewer.headers(None)
    r = client.post(
        "/internal/v1/review/decisions",
        headers=headers,
        json={
            "target_type": "disease_mapping",
            "target_id": seeded["dm"],
            "status": "rejected",
            "note": "Label is ambiguous; needs a subtype.",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert (body["previous_status"], body["review_status"], body["reviewer"]) == ("pending", "rejected", reviewer.token)
    note_only = client.post(
        "/internal/v1/review/decisions",
        headers=headers,
        json={
            "target_type": "feature_mapping",
            "target_id": seeded["fm_a"],
            "note": "Columns 3 and 9 disagree in 12 rows.",
        },
    )
    assert note_only.json()["review_status"] == "pending"  # a note alone changes no status
    with owner_db.transaction(None) as tx:
        mapping = tx.get(DiseaseMapping, seeded["dm"])
        assert (mapping.status, mapping.reviewer) == ("rejected", reviewer.token)
        notes = list(
            tx.execute(select(ReviewNote).where(ReviewNote.target_id.in_([seeded["dm"], seeded["fm_a"]]))).scalars()
        )
        assert {(n.target_type, n.status_change, n.reviewer) for n in notes} == {
            ("disease_mapping", "rejected", reviewer.token),
            ("feature_mapping", None, reviewer.token),
        }
        events = list(tx.execute(select(AuditEvent).where(AuditEvent.actor_subject == reviewer.token)).scalars())
        assert [e.redacted_metadata["to"] for e in events if e.redacted_metadata["target_id"] == seeded["dm"]] == [
            "rejected"
        ]


def test_invalid_review_requests(client, reviewer: Api, seeded):
    def post(**body):
        return client.post("/internal/v1/review/decisions", headers=reviewer.headers(None), json=body)

    assert post(target_type="disease_mapping", target_id="missing", note="n").status_code == 404
    assert post(target_type="session", target_id=seeded["dm"], note="n").json()["code"] == "unknown_review_target"
    assert (
        post(target_type="statement", target_id=seeded["st_ok"], note="n", status="published").json()["code"]
        == "invalid_review_status"
    )
    assert post(target_type="statement", target_id=seeded["st_ok"], note="   ").status_code == 422
    assert post(target_type="statement", target_id=seeded["st_ok"]).status_code == 422


# ---- reviewed-only serving ------------------------------------------------------------
def test_pending_content_never_reaches_serving(client, api: Api, reviewer: Api, seeded, owner_db):
    def condition(disease_id=seeded["dis"]):
        return client.get(f"/v1/conditions/{disease_id}", headers=api.headers(None))

    assert client.get(f"/v1/conditions/{seeded['dis']}").status_code == 401
    r = condition()
    assert r.status_code == 404 and r.json()["code"] == "condition_not_available"  # disease still pending
    assert condition(seeded["dis_old"]).status_code == 404  # a redirect to pending content is also hidden

    _approve(owner_db, Disease, seeded["dis"])
    body = condition().json()
    assert body["name"].startswith("Synthetic condition") and body["statements"] == []
    # approved-but-unsourced and approved-but-expired statements are withheld; pending ones too

    r = client.post(
        "/internal/v1/review/decisions",
        headers=reviewer.headers(None),
        json={
            "target_type": "statement",
            "target_id": seeded["st_ok"],
            "status": "approved",
            "note": "Checked against source.",
        },
    )
    assert r.status_code == 200
    shown = condition().json()["statements"]
    assert [s["statement_id"] for s in shown] == [seeded["st_ok"]]
    assert shown[0]["sources"] == [{"record_id": seeded["rec"], "source_url": "https://example.org/s"}]
    assert condition(seeded["dis_old"]).json()["disease_id"] == seeded["dis"]  # retired alias redirects

    client.post(
        "/internal/v1/review/decisions",
        headers=reviewer.headers(None),
        json={"target_type": "statement", "target_id": seeded["st_ok"], "status": "retired", "note": "Superseded."},
    )
    assert condition().json()["statements"] == []  # withdrawal takes effect immediately


def test_imported_dataset_content_is_not_served(client, api: Api):
    """Lexical candidates from the real import (when loaded) are pending and must 404."""
    for disease_id in ("dis_0082ad0d4c72303c", "fx.possibility_a", "does-not-exist"):
        assert client.get(f"/v1/conditions/{disease_id}", headers=api.headers(None)).status_code == 404


@pytest.mark.postgres
def test_database_blocks_review_writes_outside_a_reviewer_transaction(db, seeded):
    with db.transaction("dev:someone", role="user") as tx:
        changed = tx.execute(
            text("UPDATE disease_mappings SET status = 'approved' WHERE mapping_id = :m"), {"m": seeded["dm"]}
        )
        assert changed.rowcount == 0  # RLS: only a reviewer-scoped transaction may update
    with db.transaction("dev-reviewer:r", role="reviewer") as tx:
        changed = tx.execute(
            text("UPDATE disease_mappings SET status = 'approved' WHERE mapping_id = :m"), {"m": seeded["dm"]}
        )
        assert changed.rowcount == 1
        tx.rollback()
