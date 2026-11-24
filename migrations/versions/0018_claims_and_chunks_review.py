"""Claims and text chunks can be decided by a reviewer; what an approval makes (M2.5e).

Until now the single claims (`statement_claims`) were import-only: the application role had no
access. The text chunks (`evidence_chunks`) had no review status at all, so none could be approved.

1. Claims: the application role may read them and change `status`, `reviewer` and
   `applicability`, and only inside a reviewer transaction. A claim is unreviewed wording of a
   source, so even reading is for reviewers only.
2. Chunks: two new columns, `status` (pending) and `reviewer`. The application role may change
   them, and point a chunk at the statement made from it, only inside a reviewer transaction.
   Reading is for reviewers only, for the same reason.
3. What an approval makes. An approved list-item claim that names a feature becomes an evidence
   row, and an approved chunk becomes a statement with its source record. So the application role
   may now insert into `disease_feature_evidence`, `statements` and `statement_sources`, and only
   inside a reviewer transaction.
4. `superseded_by` on a claim: the version of the claim rules under which a claim that carries a
   reviewer's decision stopped being given by the rules. Such a claim is kept, never deleted.

Revision ID: 0018
Revises: 0017
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

APP = "feeltriva_app"
IS_REVIEWER = "current_setting('app.role', true) = 'reviewer'"
REVIEWERS_ONLY = {  # table -> columns a reviewer's decision may change
    "statement_claims": "status, reviewer, applicability",
    "evidence_chunks": "status, reviewer, statement_id",
}
MADE_BY_AN_APPROVAL = ("disease_feature_evidence", "statements", "statement_sources")


def upgrade() -> None:
    op.execute("ALTER TABLE statement_claims ADD COLUMN superseded_by text")
    op.execute("ALTER TABLE evidence_chunks ADD COLUMN status review_state NOT NULL DEFAULT 'pending'")
    op.execute("ALTER TABLE evidence_chunks ADD COLUMN reviewer text")
    for table, columns in REVIEWERS_ONLY.items():
        op.execute(f"GRANT SELECT ON {table} TO {APP}")
        op.execute(f"GRANT UPDATE ({columns}) ON {table} TO {APP}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({IS_REVIEWER})")
        op.execute(
            f"CREATE POLICY {table}_review ON {table} FOR UPDATE USING ({IS_REVIEWER}) WITH CHECK ({IS_REVIEWER})"
        )
    # statement_sources had no row-level security: reading stays open, as for statements.
    op.execute("ALTER TABLE statement_sources ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY statement_sources_read ON statement_sources FOR SELECT USING (true)")
    for table in MADE_BY_AN_APPROVAL:
        op.execute(f"GRANT INSERT ON {table} TO {APP}")
        op.execute(f"CREATE POLICY {table}_add ON {table} FOR INSERT WITH CHECK ({IS_REVIEWER})")


def downgrade() -> None:
    for table in MADE_BY_AN_APPROVAL:
        op.execute(f"DROP POLICY IF EXISTS {table}_add ON {table}")
        op.execute(f"REVOKE INSERT ON {table} FROM {APP}")
    op.execute("DROP POLICY IF EXISTS statement_sources_read ON statement_sources")
    op.execute("ALTER TABLE statement_sources DISABLE ROW LEVEL SECURITY")
    for table, columns in REVIEWERS_ONLY.items():
        op.execute(f"DROP POLICY IF EXISTS {table}_review ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_read ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE UPDATE ({columns}) ON {table} FROM {APP}")
    # Chunks were readable by the application role before this migration (the first grants); claims were not.
    op.execute(f"REVOKE SELECT ON statement_claims FROM {APP}")
    op.execute("ALTER TABLE evidence_chunks DROP COLUMN reviewer")
    op.execute("ALTER TABLE evidence_chunks DROP COLUMN status")
    op.execute("ALTER TABLE statement_claims DROP COLUMN superseded_by")
