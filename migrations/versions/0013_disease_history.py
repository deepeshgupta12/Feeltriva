"""Disease redirects with a history of merges and splits (M2.5c1).

A merge points one disease label at another, the kept one (`diseases.redirected_to`, there since
the first migration). This migration adds the history: every merge and every split is one row,
with the reviewer and the reason, and the rows are never changed or deleted.

The application role may now change `redirected_to`, `preferred_name` and `status` of a disease
and add a history row, and only inside a reviewer transaction. Reading stays as it was.

Revision ID: 0013
Revises: 0012
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

APP = "feeltriva_app"
IS_REVIEWER = "current_setting('app.role', true) = 'reviewer'"


def upgrade() -> None:
    op.execute(
        """CREATE TABLE disease_history (
               event_id uuid PRIMARY KEY,
               action text NOT NULL CHECK (action IN ('merge', 'split')),
               disease_id text NOT NULL REFERENCES diseases,
               other_id text NOT NULL REFERENCES diseases,
               detail jsonb NOT NULL DEFAULT '{}',
               reviewer text NOT NULL,
               note text NOT NULL,
               created_at timestamptz NOT NULL DEFAULT now(),
               CHECK (disease_id <> other_id)
           )"""
    )
    op.execute("CREATE INDEX disease_history_disease ON disease_history (disease_id, created_at)")
    op.execute("CREATE INDEX disease_history_other ON disease_history (other_id, created_at)")
    op.execute(
        """CREATE FUNCTION disease_history_append_only() RETURNS trigger AS $$
           BEGIN
               RAISE EXCEPTION 'the history of merges and splits cannot be changed';
           END $$ LANGUAGE plpgsql"""
    )
    op.execute(
        "CREATE TRIGGER disease_history_append_only BEFORE UPDATE OR DELETE ON disease_history "
        "FOR EACH ROW EXECUTE FUNCTION disease_history_append_only()"
    )
    op.execute(f"GRANT SELECT, INSERT ON disease_history TO {APP}")
    op.execute("ALTER TABLE disease_history ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY disease_history_read ON disease_history FOR SELECT USING (true)")
    op.execute(f"CREATE POLICY disease_history_add ON disease_history FOR INSERT WITH CHECK ({IS_REVIEWER})")
    op.execute(f"GRANT UPDATE (redirected_to, preferred_name, status) ON diseases TO {APP}")
    op.execute("ALTER TABLE diseases ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY diseases_read ON diseases FOR SELECT USING (true)")
    op.execute(f"CREATE POLICY diseases_review ON diseases FOR UPDATE USING ({IS_REVIEWER}) WITH CHECK ({IS_REVIEWER})")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS diseases_review ON diseases")
    op.execute("DROP POLICY IF EXISTS diseases_read ON diseases")
    op.execute("ALTER TABLE diseases DISABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE UPDATE (redirected_to, preferred_name, status) ON diseases FROM {APP}")
    op.execute("DROP TABLE disease_history")
    op.execute("DROP FUNCTION disease_history_append_only()")
