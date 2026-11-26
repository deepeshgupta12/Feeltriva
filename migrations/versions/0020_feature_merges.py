"""Merging the names of symptoms and other items, with a history (M2.20).

Two names for one item ("cross eyed", "cross-eyed") are merged as two condition names are
(migration 0013): one is kept, the other points at it (`features.redirected_to`), is set to
`retired` and stays in the database, so its name remains another name of the kept item and every
column, fact and sentence that carries it keeps what it was given. `feature_history` holds one row
for every merge and split, with the reviewer's name and reason; it is never changed or deleted.

The application role may now set `redirected_to` of an item, as it may already set its status,
and only inside a reviewer's transaction (the policy of migration 0014).

Revision ID: 0020
Revises: 0019
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

APP = "feeltriva_app"
IS_REVIEWER = "current_setting('app.role', true) = 'reviewer'"


def upgrade() -> None:
    op.execute("ALTER TABLE features ADD COLUMN redirected_to text REFERENCES features")
    op.execute(
        "ALTER TABLE features ADD CONSTRAINT features_not_merged_into_itself "
        "CHECK (redirected_to IS NULL OR redirected_to <> feature_id)"
    )
    op.execute("CREATE INDEX features_redirected_to ON features (redirected_to) WHERE redirected_to IS NOT NULL")
    op.execute(
        """CREATE TABLE feature_history (
               event_id uuid PRIMARY KEY,
               action text NOT NULL CHECK (action IN ('merge', 'split')),
               feature_id text NOT NULL REFERENCES features,
               other_id text NOT NULL REFERENCES features,
               detail jsonb NOT NULL DEFAULT '{}',
               reviewer text NOT NULL,
               note text NOT NULL,
               created_at timestamptz NOT NULL DEFAULT now(),
               CHECK (feature_id <> other_id)
           )"""
    )
    op.execute("CREATE INDEX feature_history_feature ON feature_history (feature_id, created_at)")
    op.execute("CREATE INDEX feature_history_other ON feature_history (other_id, created_at)")
    op.execute(
        """CREATE FUNCTION feature_history_append_only() RETURNS trigger AS $$
           BEGIN
               RAISE EXCEPTION 'the history of merges and splits cannot be changed';
           END $$ LANGUAGE plpgsql"""
    )
    op.execute(
        "CREATE TRIGGER feature_history_append_only BEFORE UPDATE OR DELETE ON feature_history "
        "FOR EACH ROW EXECUTE FUNCTION feature_history_append_only()"
    )
    op.execute(f"GRANT SELECT, INSERT ON feature_history TO {APP}")
    op.execute("ALTER TABLE feature_history ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY feature_history_read ON feature_history FOR SELECT USING (true)")
    op.execute(f"CREATE POLICY feature_history_add ON feature_history FOR INSERT WITH CHECK ({IS_REVIEWER})")
    op.execute(f"GRANT UPDATE (redirected_to) ON features TO {APP}")


def downgrade() -> None:
    op.execute(f"REVOKE UPDATE (redirected_to) ON features FROM {APP}")
    op.execute("DROP TABLE feature_history")
    op.execute("DROP FUNCTION feature_history_append_only()")
    op.execute("DROP INDEX features_redirected_to")
    op.execute("ALTER TABLE features DROP CONSTRAINT features_not_merged_into_itself")
    op.execute("ALTER TABLE features DROP COLUMN redirected_to")
