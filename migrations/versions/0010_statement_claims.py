"""Single claims taken from narrative statements, for review (M2.6).

One row is a piece of a stored statement between two character offsets: a sentence, or an item
of an enumeration inside a sentence. It never holds new wording. A list item may carry the
feature whose name it is exactly, as a proposal. Every row is `pending` until a reviewer decides;
applicability stays empty until a reviewer sets it.

Import-only for now: the application role gets no access. The review screens (M2.4) will read
these rows through a reviewer-only path.

Revision ID: 0010
Revises: 0009
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE statement_claims (
            claim_id text PRIMARY KEY,
            statement_id text NOT NULL REFERENCES statements,
            parent_claim_id text REFERENCES statement_claims,
            kind text NOT NULL CHECK (kind IN ('sentence', 'list_item')),
            span_start integer NOT NULL,
            span_end integer NOT NULL,
            claim_text text NOT NULL,
            rule text NOT NULL,
            cues jsonb NOT NULL DEFAULT '{}',
            proposed_feature_id text REFERENCES features,
            applicability jsonb,
            status review_state NOT NULL DEFAULT 'pending',
            reviewer text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK (span_start >= 0 AND span_end > span_start),
            CHECK ((kind = 'list_item') = (parent_claim_id IS NOT NULL)),
            UNIQUE (statement_id, kind, span_start, span_end)
        )"""
    )
    op.execute("CREATE INDEX statement_claims_statement ON statement_claims (statement_id, span_start)")
    op.execute(
        "CREATE INDEX statement_claims_feature ON statement_claims (proposed_feature_id) WHERE proposed_feature_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS statement_claims")
