"""Least-privilege application role and forced row-level security on private session data.

The API connects as feeltriva_app (not the schema owner, not a superuser) and binds the
verified caller to each transaction with set_config('app.owner_subject', ...). Policies then
scope every session row and child row to that caller even if a query omits its owner filter.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

APP = "feeltriva_app"
OWNER = "current_setting('app.owner_subject', true)"
IS_REVIEWER = "current_setting('app.role', true) = 'reviewer'"
SESSION_CHILDREN = ["session_messages", "session_observations", "session_answers", "assessments"]
REFERENCE = [
    "sources", "source_records", "mapping_releases", "diseases", "disease_mappings", "features",
    "feature_mappings", "statements", "statement_sources", "disease_feature_evidence", "knowledge_releases",
    "evidence_chunks", "rule_bundles", "clinical_rules", "followup_questions", "model_releases", "review_notes",
]
REVIEWABLE = {
    "disease_mappings": "status, reviewer",
    "feature_mappings": "status",
    "statements": "status, reviewed_by, reviewed_at",
}


def upgrade() -> None:
    op.execute(
        f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP}') THEN
                CREATE ROLE {APP} NOLOGIN;
            END IF;
        END $$"""
    )
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP}")
    op.execute(f"GRANT SELECT ON {', '.join(REFERENCE)} TO {APP}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON sessions, {', '.join(SESSION_CHILDREN)}, idempotency_keys TO {APP}"
    )
    op.execute(f"GRANT SELECT, INSERT ON audit_events TO {APP}")
    op.execute(f"GRANT INSERT ON review_notes TO {APP}")
    for table, columns in REVIEWABLE.items():
        op.execute(f"GRANT UPDATE ({columns}) ON {table} TO {APP}")

    op.execute("ALTER TABLE sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sessions FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY sessions_owner ON sessions USING (owner_subject = {OWNER}) WITH CHECK (owner_subject = {OWNER})")
    for table in SESSION_CHILDREN:
        visible = f"EXISTS (SELECT 1 FROM sessions s WHERE s.session_id = {table}.session_id)"
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_owner ON {table} USING ({visible}) WITH CHECK ({visible})")
    for table, column in (("idempotency_keys", "owner_subject"), ("audit_events", "actor_subject")):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_owner ON {table} USING ({column} = {OWNER}) WITH CHECK ({column} = {OWNER})")

    # Review content is readable by the service; only a reviewer-scoped transaction may change it.
    for table in REVIEWABLE:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING (true)")
        op.execute(f"CREATE POLICY {table}_review ON {table} FOR UPDATE USING ({IS_REVIEWER}) WITH CHECK ({IS_REVIEWER})")
    op.execute("ALTER TABLE review_notes ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY review_notes_read ON review_notes FOR SELECT USING (true)")
    op.execute(
        f"CREATE POLICY review_notes_write ON review_notes FOR INSERT WITH CHECK ({IS_REVIEWER} AND reviewer = {OWNER})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS review_notes_write ON review_notes")
    op.execute("DROP POLICY IF EXISTS review_notes_read ON review_notes")
    op.execute("ALTER TABLE review_notes DISABLE ROW LEVEL SECURITY")
    for table in REVIEWABLE:
        op.execute(f"DROP POLICY IF EXISTS {table}_review ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_read ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table in ["idempotency_keys", "audit_events", *SESSION_CHILDREN, "sessions"]:
        op.execute(f"DROP POLICY IF EXISTS {table}_owner ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP}")
    # The role itself is left in place: other databases in the cluster may use it.
