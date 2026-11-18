"""Suggested relations between candidates, for a reviewer to accept or reject (M2.8).

One row per suggested pair of disease candidates or of feature candidates: that the two may be
the same thing under different wording (`possible_synonym`), or that the left one is a narrower
form of the right one (`possible_subtype`). A row keeps both terms and the reasons for the
suggestion. Nothing is merged by a suggestion; a decision is recorded with the reviewer's name
and stays, so a rejected pair is not suggested again.

The API role may read and decide these rows only inside a reviewer transaction.

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

APP = "feeltriva_app"
IS_REVIEWER = "current_setting('app.role', true) = 'reviewer'"


def upgrade() -> None:
    op.execute(
        """CREATE TABLE relation_suggestions (
            suggestion_id text PRIMARY KEY,
            subject_type text NOT NULL CHECK (subject_type IN ('disease', 'feature')),
            relation text NOT NULL CHECK (relation IN ('possible_synonym', 'possible_subtype')),
            left_id text NOT NULL,
            right_id text NOT NULL,
            left_label text NOT NULL,
            right_label text NOT NULL,
            signals jsonb NOT NULL DEFAULT '[]',
            status review_state NOT NULL DEFAULT 'pending',
            reviewer text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK (left_id <> right_id)
        )"""
    )
    op.execute("CREATE INDEX relation_suggestions_status ON relation_suggestions (status, subject_type, relation)")
    op.execute(f"GRANT SELECT ON relation_suggestions TO {APP}")
    op.execute(f"GRANT UPDATE (status, reviewer) ON relation_suggestions TO {APP}")
    op.execute("ALTER TABLE relation_suggestions ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY relation_suggestions_read ON relation_suggestions FOR SELECT USING ({IS_REVIEWER})")
    op.execute(
        f"CREATE POLICY relation_suggestions_review ON relation_suggestions FOR UPDATE USING ({IS_REVIEWER}) "
        f"WITH CHECK ({IS_REVIEWER})"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS relation_suggestions")
