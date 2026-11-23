"""Published rule releases: immutable, numbered, one of them current (M2.5b).

A release is a snapshot of the approved rules of an approved bundle, with the sources the rules
rest on, as it was published: who published it, when, and its SHA-256. The database refuses any
change to a published release and any deletion; only which release is current can change, which
is how a rollback is done. At most one release is current.

The application role may read releases, publish one and change which one is current, and only
inside a reviewer transaction.

Revision ID: 0012
Revises: 0011
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

APP = "feeltriva_app"
IS_REVIEWER = "current_setting('app.role', true) = 'reviewer'"


def upgrade() -> None:
    op.execute(
        """CREATE TABLE rule_releases (
               release_id text PRIMARY KEY,
               bundle_id text NOT NULL REFERENCES rule_bundles,
               number integer NOT NULL CHECK (number > 0),
               content jsonb NOT NULL,
               sha256 text NOT NULL,
               rule_file_fingerprint text,
               published_by text NOT NULL,
               published_at timestamptz NOT NULL DEFAULT now(),
               is_current boolean NOT NULL DEFAULT false,
               UNIQUE (bundle_id, number)
           )"""
    )
    op.execute("CREATE UNIQUE INDEX rule_releases_one_current ON rule_releases (is_current) WHERE is_current")
    op.execute(
        """CREATE FUNCTION rule_releases_immutable() RETURNS trigger AS $$
           BEGIN
               IF TG_OP = 'DELETE' THEN
                   RAISE EXCEPTION 'a published release cannot be deleted';
               END IF;
               IF (NEW.release_id, NEW.bundle_id, NEW.number, NEW.content, NEW.sha256, NEW.rule_file_fingerprint,
                   NEW.published_by, NEW.published_at)
                  IS DISTINCT FROM
                  (OLD.release_id, OLD.bundle_id, OLD.number, OLD.content, OLD.sha256, OLD.rule_file_fingerprint,
                   OLD.published_by, OLD.published_at) THEN
                   RAISE EXCEPTION 'a published release cannot be edited';
               END IF;
               RETURN NEW;
           END $$ LANGUAGE plpgsql"""
    )
    op.execute(
        "CREATE TRIGGER rule_releases_immutable BEFORE UPDATE OR DELETE ON rule_releases "
        "FOR EACH ROW EXECUTE FUNCTION rule_releases_immutable()"
    )
    op.execute(f"GRANT SELECT, INSERT ON rule_releases TO {APP}")
    op.execute(f"GRANT UPDATE (is_current) ON rule_releases TO {APP}")
    op.execute("ALTER TABLE rule_releases ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY rule_releases_read ON rule_releases FOR SELECT USING (true)")
    op.execute(f"CREATE POLICY rule_releases_publish ON rule_releases FOR INSERT WITH CHECK ({IS_REVIEWER})")
    op.execute(
        f"CREATE POLICY rule_releases_switch ON rule_releases FOR UPDATE USING ({IS_REVIEWER}) WITH CHECK ({IS_REVIEWER})"
    )


def downgrade() -> None:
    op.execute("DROP TABLE rule_releases")
    op.execute("DROP FUNCTION rule_releases_immutable()")
