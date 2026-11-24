"""The serving views: only what is published, still approved, sourced and not expired (M2.9). Invented rows.

PostgreSQL only: the views are created by the migrations. The rows are those of the knowledge-release tests:
seven statements and six evidence rows, one for each way of being published, held back or left out.
"""

from __future__ import annotations

import uuid

import pytest
from feeltriva_api.models import Statement, StatementSource
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.api.test_knowledge_releases import _approve_all, _decide, _publish, _rows
from tests.conftest import Api

pytestmark = pytest.mark.postgres
MAPPINGS = "/internal/v1/review/mapping-releases"
VIEWS = (
    "reviewed_disease_catalog",
    "reviewed_condition_statements",
    "reviewed_care_statements",
    "reviewed_disease_feature_edges",
)


@pytest.fixture
def reviewer(client) -> Api:
    name = f"rev-{uuid.uuid4().hex[:8]}"
    return Api(client, subject=name, token=f"dev-reviewer:{name}")


@pytest.fixture
def tag(owner_db) -> str:
    """The rows of the knowledge-release tests, and one more statement, about treatment, for the care view."""
    tag = uuid.uuid4().hex[:10]
    _rows(owner_db, tag)
    with owner_db.transaction(None, role="migration") as tx:
        tx.add(
            Statement(
                statement_id=f"st_{tag}_t",
                disease_id=f"dis_{tag}_kept",
                statement_type="treatment",
                text_content=f"A sample sentence about care for a pretend ache ({tag}).",
            )
        )
        tx.flush()
        tx.add(
            StatementSource(
                statement_id=f"st_{tag}_t", record_id=f"rec_{tag}_1", source_url="https://example.org/sample"
            )
        )
    return tag


def _view(db, view: str, tag: str, column: str) -> list[str]:
    """The values of one column of a view for this test's rows, read as the application role in a user's transaction."""
    key = "disease_id"
    with db.transaction("someone") as tx:
        rows = tx.execute(text(f"SELECT {column} FROM {view} WHERE {key} LIKE :t ORDER BY 1"), {"t": f"%{tag}%"})  # noqa: S608
        return [row[0] for row in rows]


def _shown(db, tag: str) -> dict[str, list[str]]:
    letter = len(f"st_{tag}_")
    return {
        "catalog": [value.removeprefix(f"dis_{tag}_") for value in _view(db, VIEWS[0], tag, "disease_id")],
        "statements": [value[letter:] for value in _view(db, VIEWS[1], tag, "statement_id")],
        "care": [value[letter:] for value in _view(db, VIEWS[2], tag, "statement_id")],
        "edges": [value.removeprefix(f"ev_{tag}_") for value in _view(db, VIEWS[3], tag, "evidence_id")],
    }


def test_the_views_hold_only_what_is_published_and_a_withdrawal_takes_effect_at_once(
    client, api: Api, reviewer: Api, tag, db, owner_db
):
    kept, alias = f"dis_{tag}_kept", f"dis_{tag}_alias"
    nothing = {"catalog": [], "statements": [], "care": [], "edges": []}

    def decide(target_type: str, target_id: str, status: str) -> None:
        assert _decide(client, reviewer, target_type, target_id, status).status_code == 200, (target_type, status)

    def condition(disease_id: str = kept):
        return client.get(f"/v1/conditions/{disease_id}", headers=api.headers(None))

    # Nothing decided: nothing is in any view.
    assert _shown(db, tag) == nothing
    # Approved and the mapping release published: the disease is in the catalog. The approved statements and
    # evidence are in no view, because no knowledge release holds them.
    _approve_all(client, reviewer, tag)
    decide("statement", f"st_{tag}_t", "approved")
    assert _shown(db, tag) == {**nothing, "catalog": ["kept"]}
    with db.transaction("someone") as tx:
        row = tx.execute(text(f"SELECT * FROM {VIEWS[0]} WHERE disease_id = :d"), {"d": kept}).mappings().one()  # noqa: S608
    assert (row["name"], row["aliases"], row["merged_labels"], row["mapping_release"]) == (
        f"pretend ache {tag}",
        [f"ache, pretend {tag}"],
        [alias],
        f"map-{tag}.r1",
    )
    assert condition().json()["statements"] == []
    # The knowledge release published: of eight statements three are shown, of six evidence rows two. The pending
    # ones, the expired one, the one without a source, the one of the source that is not approved, and what
    # stands under the label that is not approved are in no view.
    assert _publish(client, reviewer, tag).status_code == 200
    published = {"catalog": ["kept"], "statements": ["a", "b", "t"], "care": ["t"], "edges": ["1", "2"]}
    assert _shown(db, tag) == published
    with db.transaction("someone") as tx:
        rows = tx.execute(
            text(f"SELECT * FROM {VIEWS[1]} WHERE statement_id = :s"),  # noqa: S608
            {"s": f"st_{tag}_b"},
        ).mappings()
        statement = rows.one()
    # The statement of the merged label stands under the label kept; it carries the source record it rests on.
    assert (statement["disease_id"], statement["knowledge_release"]) == (kept, f"know-{tag}.r1")
    assert statement["sources"] == [
        {"record_id": f"rec_{tag}_1", "source_id": f"src_{tag}_ok", "source_url": "https://example.org/sample"}
    ]
    # The condition route reads these views: the same three statements, under either label.
    served = condition().json()
    assert [entry["statement_id"] for entry in served["statements"]] == [f"st_{tag}_{key}" for key in "abt"]
    assert served["statements"][0]["sources"] == [
        {"record_id": f"rec_{tag}_1", "source_url": "https://example.org/sample"}
    ]
    assert condition(alias).json()["disease_id"] == kept
    assert condition(f"dis_{tag}_other").status_code == 404  # a label that is not approved

    # Each withdrawal takes effect at once, without a new release, and is undone by restoring the approval.
    decide("statement", f"st_{tag}_a", "retired")
    assert _shown(db, tag) == {**published, "statements": ["b", "t"], "edges": ["1"]}  # its evidence row goes too
    decide("statement", f"st_{tag}_a", "approved")
    assert _shown(db, tag) == published
    with owner_db.transaction(None, role="migration") as tx:  # a statement that has expired since it was published
        tx.execute(
            text("UPDATE statements SET expires_at = now() - interval '1 day' WHERE statement_id = :s"),
            {"s": f"st_{tag}_b"},
        )
    assert _shown(db, tag)["statements"] == ["a", "t"]
    with owner_db.transaction(None, role="migration") as tx:
        tx.execute(text("UPDATE statements SET expires_at = NULL WHERE statement_id = :s"), {"s": f"st_{tag}_b"})
    decide("evidence", f"ev_{tag}_1", "rejected")
    assert _shown(db, tag) == {**published, "edges": ["2"]}
    decide("evidence", f"ev_{tag}_1", "approved")
    decide("feature", f"feat_{tag}_hat", "retired")
    assert _shown(db, tag) == {**published, "edges": []}
    decide("feature", f"feat_{tag}_hat", "approved")
    # Rights: when the approval of the source is withdrawn, everything that rests on it goes.
    decide("source", f"src_{tag}_ok", "pending")
    assert _shown(db, tag) == {**nothing, "catalog": ["kept"]}
    decide("source", f"src_{tag}_ok", "approved")
    assert _shown(db, tag) == published
    decide("disease", kept, "rejected")
    assert _shown(db, tag) == nothing and condition().status_code == 404
    decide("disease", kept, "approved")
    assert _shown(db, tag) == published

    # A knowledge release is read with the mapping release it was published against. A later mapping release
    # becomes current: the disease is still in the catalog, the knowledge views are empty.
    decide("feature", f"feat_{tag}_coat", "approved")
    body = {"mapping_release_id": f"map-{tag}", "note": "Publish in a test."}
    assert client.post(MAPPINGS, headers=reviewer.headers(None), json=body).status_code == 200
    assert _shown(db, tag) == {**nothing, "catalog": ["kept"]}
    assert condition().json()["statements"] == []
    # Rolled back to the mapping release the knowledge was published against, it is shown again.
    back = {"release_id": f"map-{tag}.r1", "note": "Roll back."}
    assert client.post(f"{MAPPINGS}/current", headers=reviewer.headers(None), json=back).status_code == 200
    assert _shown(db, tag) == published


def test_the_application_role_reads_the_views_and_cannot_write_through_them(db):
    for view in VIEWS:
        with db.transaction("someone") as tx:
            tx.execute(text(f"SELECT count(*) FROM {view}")).scalar_one()  # noqa: S608
    for statement in (
        "UPDATE reviewed_disease_catalog SET name = 'another name'",
        "DELETE FROM reviewed_condition_statements",
        "INSERT INTO reviewed_care_statements (statement_id) VALUES ('x')",
    ):
        with pytest.raises(DBAPIError), db.transaction("someone", role="reviewer") as tx:
            tx.execute(text(statement))
