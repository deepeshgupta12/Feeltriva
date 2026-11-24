"""The response texts of a release, stored for a reviewer's decision (M2.5f).

Every release bundle carries four texts a person is shown outside the rules. They are drafted in a
file. This table holds them as they were stored from that file, with the file's SHA-256, so that a
reviewer's approval is for exactly the words that were read. The texts of a set that has been
decided cannot be changed: the database refuses it, also to the owner of the schema. A changed
text is stored after the decision is withdrawn, and is then decided again.

The application role may read the sets and, only inside a reviewer transaction, change the status
and the approval fields. It cannot change a text.

Revision ID: 0016
Revises: 0015
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

APP = "feeltriva_app"
IS_REVIEWER = "current_setting('app.role', true) = 'reviewer'"


def upgrade() -> None:
    op.execute(
        """CREATE TABLE response_text_sets (
               set_id text PRIMARY KEY,
               version text UNIQUE NOT NULL,
               fingerprint text NOT NULL,
               texts jsonb NOT NULL,
               status review_state NOT NULL DEFAULT 'pending',
               approved_by text,
               approved_at timestamptz
           )"""
    )
    op.execute(
        """CREATE FUNCTION response_text_sets_decided() RETURNS trigger AS $$
           BEGIN
               IF OLD.status <> 'pending' AND (NEW.version, NEW.fingerprint, NEW.texts)
                  IS DISTINCT FROM (OLD.version, OLD.fingerprint, OLD.texts) THEN
                   RAISE EXCEPTION 'the texts of a decided set cannot be changed';
               END IF;
               RETURN NEW;
           END $$ LANGUAGE plpgsql"""
    )
    op.execute(
        "CREATE TRIGGER response_text_sets_decided BEFORE UPDATE ON response_text_sets "
        "FOR EACH ROW EXECUTE FUNCTION response_text_sets_decided()"
    )
    op.execute(f"GRANT SELECT ON response_text_sets TO {APP}")
    op.execute(f"GRANT UPDATE (status, approved_by, approved_at) ON response_text_sets TO {APP}")
    op.execute("ALTER TABLE response_text_sets ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY response_text_sets_read ON response_text_sets FOR SELECT USING (true)")
    op.execute(
        "CREATE POLICY response_text_sets_review ON response_text_sets FOR UPDATE "
        f"USING ({IS_REVIEWER}) WITH CHECK ({IS_REVIEWER})"
    )


def downgrade() -> None:
    op.execute("DROP TABLE response_text_sets")
    op.execute("DROP FUNCTION response_text_sets_decided()")
