"""Vocabulary links can be decided through the review path (M2.17).

Until now the application role had no access to `terminology_links`. A reviewer's decision is
recorded through the review API, which runs as the application role, so that role may now read
the rows and change `status` and `reviewer`, and only inside a reviewer transaction: row-level
security hides every row from any other transaction. It cannot change a code, a title or any
other column, and cannot insert or delete a link.

Codes stay internal (decision E63): no user-facing route reads this table, and a transaction
that is not a reviewer's sees no row of it.

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

APP = "feeltriva_app"
IS_REVIEWER = "current_setting('app.role', true) = 'reviewer'"


def upgrade() -> None:
    op.execute(f"GRANT SELECT ON terminology_links TO {APP}")
    op.execute(f"GRANT UPDATE (status, reviewer) ON terminology_links TO {APP}")
    op.execute("ALTER TABLE terminology_links ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY terminology_links_read ON terminology_links FOR SELECT USING ({IS_REVIEWER})")
    op.execute(
        f"CREATE POLICY terminology_links_review ON terminology_links FOR UPDATE USING ({IS_REVIEWER}) "
        f"WITH CHECK ({IS_REVIEWER})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS terminology_links_review ON terminology_links")
    op.execute("DROP POLICY IF EXISTS terminology_links_read ON terminology_links")
    op.execute("ALTER TABLE terminology_links DISABLE ROW LEVEL SECURITY")
    op.execute(f"REVOKE ALL ON terminology_links FROM {APP}")
