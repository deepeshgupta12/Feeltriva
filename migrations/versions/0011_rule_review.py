"""Rules, questions and rule bundles can be decided through the review path (M2.5a).

Until now the application role could read `clinical_rules`, `followup_questions` and
`rule_bundles` and change nothing in them. A reviewer's decision is recorded through the review
API, which runs as the application role, so that role may now change the status of a rule or a
question, and the status and the approval fields of a bundle, and only inside a reviewer
transaction: row-level security refuses the change in any other transaction. It cannot change a
condition, a text, a priority or any other column, and cannot insert or delete a row.

Reading stays as it was. Serving does not read these tables: it reads a published release bundle.

Revision ID: 0011
Revises: 0010
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

APP = "feeltriva_app"
IS_REVIEWER = "current_setting('app.role', true) = 'reviewer'"
DECIDABLE = {
    "clinical_rules": "status",
    "followup_questions": "status",
    "rule_bundles": "status, approved_by, approved_at",
}


def upgrade() -> None:
    for table, columns in DECIDABLE.items():
        op.execute(f"GRANT UPDATE ({columns}) ON {table} TO {APP}")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING (true)")
        op.execute(
            f"CREATE POLICY {table}_review ON {table} FOR UPDATE USING ({IS_REVIEWER}) WITH CHECK ({IS_REVIEWER})"
        )


def downgrade() -> None:
    for table, columns in DECIDABLE.items():
        op.execute(f"DROP POLICY IF EXISTS {table}_review ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_read ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE UPDATE ({columns}) ON {table} FROM {APP}")
