"""Features can be decided by a reviewer; published mapping releases (M2.5c2).

Two things.

1. Until now the application role could read `features` and change nothing in them. A reviewer's
   decision is recorded through the review API, which runs as the application role, so that role
   may now change the status of a feature, and only inside a reviewer transaction. It cannot
   change a name, a kind or any other column. (Diseases got the same in migration 0013.)

2. `published_mappings`: a published mapping release is a numbered snapshot of what was approved
   in a mapping working set (`mapping_releases`) at the time: features, diseases with their
   synonyms and redirects, and the mappings of source labels and columns to them. The database
   refuses any change to a published release and any deletion; only which release is current can
   change, which is how a rollback is done. At most one release is current. The application role
   may read releases, publish one and change which one is current, and only inside a reviewer
   transaction.

A published mapping release holds no code of an outside vocabulary (decision E63).

Revision ID: 0014
Revises: 0013
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

APP = "feeltriva_app"
IS_REVIEWER = "current_setting('app.role', true) = 'reviewer'"


def upgrade() -> None:
    op.execute(f"GRANT UPDATE (status) ON features TO {APP}")
    op.execute("ALTER TABLE features ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY features_read ON features FOR SELECT USING (true)")
    op.execute(f"CREATE POLICY features_review ON features FOR UPDATE USING ({IS_REVIEWER}) WITH CHECK ({IS_REVIEWER})")
    op.execute(
        """CREATE TABLE published_mappings (
               release_id text PRIMARY KEY,
               mapping_release_id text NOT NULL REFERENCES mapping_releases,
               number integer NOT NULL CHECK (number > 0),
               content jsonb NOT NULL,
               sha256 text NOT NULL,
               published_by text NOT NULL,
               published_at timestamptz NOT NULL DEFAULT now(),
               is_current boolean NOT NULL DEFAULT false,
               UNIQUE (mapping_release_id, number)
           )"""
    )
    op.execute("CREATE UNIQUE INDEX published_mappings_one_current ON published_mappings (is_current) WHERE is_current")
    op.execute(
        """CREATE FUNCTION published_mappings_immutable() RETURNS trigger AS $$
           BEGIN
               IF TG_OP = 'DELETE' THEN
                   RAISE EXCEPTION 'a published release cannot be deleted';
               END IF;
               IF (NEW.release_id, NEW.mapping_release_id, NEW.number, NEW.content, NEW.sha256,
                   NEW.published_by, NEW.published_at)
                  IS DISTINCT FROM
                  (OLD.release_id, OLD.mapping_release_id, OLD.number, OLD.content, OLD.sha256,
                   OLD.published_by, OLD.published_at) THEN
                   RAISE EXCEPTION 'a published release cannot be edited';
               END IF;
               RETURN NEW;
           END $$ LANGUAGE plpgsql"""
    )
    op.execute(
        "CREATE TRIGGER published_mappings_immutable BEFORE UPDATE OR DELETE ON published_mappings "
        "FOR EACH ROW EXECUTE FUNCTION published_mappings_immutable()"
    )
    op.execute(f"GRANT SELECT, INSERT ON published_mappings TO {APP}")
    op.execute(f"GRANT UPDATE (is_current) ON published_mappings TO {APP}")
    op.execute("ALTER TABLE published_mappings ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY published_mappings_read ON published_mappings FOR SELECT USING (true)")
    op.execute(f"CREATE POLICY published_mappings_publish ON published_mappings FOR INSERT WITH CHECK ({IS_REVIEWER})")
    op.execute(
        "CREATE POLICY published_mappings_switch ON published_mappings FOR UPDATE "
        f"USING ({IS_REVIEWER}) WITH CHECK ({IS_REVIEWER})"
    )


def downgrade() -> None:
    op.execute("DROP TABLE published_mappings")
    op.execute("DROP FUNCTION published_mappings_immutable()")
    op.execute("DROP POLICY IF EXISTS features_review ON features")
    op.execute("DROP POLICY IF EXISTS features_read ON features")
    op.execute("ALTER TABLE features DISABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE UPDATE (status) ON features FROM {APP}")
