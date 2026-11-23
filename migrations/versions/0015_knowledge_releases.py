"""Evidence and sources can be decided by a reviewer; published knowledge releases (M2.5c3).

Two things.

1. Until now the application role could read `disease_feature_evidence` and `sources` and change
   nothing in them. A reviewer's decision is recorded through the review API, which runs as the
   application role, so that role may now change the status of an evidence row and the provenance
   status of a source (the decision that its licence and origin allow its content to be used),
   and only inside a reviewer transaction. It cannot change any other column.

2. `published_knowledge`: a published knowledge release is a numbered snapshot of the approved
   statements and evidence at the time, pinned to the mapping release that was current. The
   database refuses any change to a published release and any deletion; only which release is
   current can change, which is how a rollback is done. At most one release is current. The
   application role may read releases, publish one and change which one is current, and only
   inside a reviewer transaction.

Revision ID: 0015
Revises: 0014
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

APP = "feeltriva_app"
IS_REVIEWER = "current_setting('app.role', true) = 'reviewer'"
DECIDABLE = {"disease_feature_evidence": "status", "sources": "provenance_status"}


def upgrade() -> None:
    for table, columns in DECIDABLE.items():
        op.execute(f"GRANT UPDATE ({columns}) ON {table} TO {APP}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING (true)")
        op.execute(
            f"CREATE POLICY {table}_review ON {table} FOR UPDATE USING ({IS_REVIEWER}) WITH CHECK ({IS_REVIEWER})"
        )
    op.execute(
        """CREATE TABLE published_knowledge (
               release_id text PRIMARY KEY,
               knowledge_release_id text NOT NULL REFERENCES knowledge_releases,
               mapping_release text NOT NULL REFERENCES published_mappings,
               number integer NOT NULL CHECK (number > 0),
               content jsonb NOT NULL,
               sha256 text NOT NULL,
               published_by text NOT NULL,
               published_at timestamptz NOT NULL DEFAULT now(),
               is_current boolean NOT NULL DEFAULT false,
               UNIQUE (knowledge_release_id, number)
           )"""
    )
    op.execute(
        "CREATE UNIQUE INDEX published_knowledge_one_current ON published_knowledge (is_current) WHERE is_current"
    )
    op.execute(
        """CREATE FUNCTION published_knowledge_immutable() RETURNS trigger AS $$
           BEGIN
               IF TG_OP = 'DELETE' THEN
                   RAISE EXCEPTION 'a published release cannot be deleted';
               END IF;
               IF (NEW.release_id, NEW.knowledge_release_id, NEW.mapping_release, NEW.number, NEW.content,
                   NEW.sha256, NEW.published_by, NEW.published_at)
                  IS DISTINCT FROM
                  (OLD.release_id, OLD.knowledge_release_id, OLD.mapping_release, OLD.number, OLD.content,
                   OLD.sha256, OLD.published_by, OLD.published_at) THEN
                   RAISE EXCEPTION 'a published release cannot be edited';
               END IF;
               RETURN NEW;
           END $$ LANGUAGE plpgsql"""
    )
    op.execute(
        "CREATE TRIGGER published_knowledge_immutable BEFORE UPDATE OR DELETE ON published_knowledge "
        "FOR EACH ROW EXECUTE FUNCTION published_knowledge_immutable()"
    )
    op.execute(f"GRANT SELECT, INSERT ON published_knowledge TO {APP}")
    op.execute(f"GRANT UPDATE (is_current) ON published_knowledge TO {APP}")
    op.execute("ALTER TABLE published_knowledge ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY published_knowledge_read ON published_knowledge FOR SELECT USING (true)")
    op.execute(
        f"CREATE POLICY published_knowledge_publish ON published_knowledge FOR INSERT WITH CHECK ({IS_REVIEWER})"
    )
    op.execute(
        "CREATE POLICY published_knowledge_switch ON published_knowledge FOR UPDATE "
        f"USING ({IS_REVIEWER}) WITH CHECK ({IS_REVIEWER})"
    )


def downgrade() -> None:
    op.execute("DROP TABLE published_knowledge")
    op.execute("DROP FUNCTION published_knowledge_immutable()")
    for table, columns in DECIDABLE.items():
        op.execute(f"DROP POLICY IF EXISTS {table}_review ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_read ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE UPDATE ({columns}) ON {table} FROM {APP}")
