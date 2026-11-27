"""Whether a person agreed to their conversation being used to improve the product (M3.16).

Kept on the session beside the consent version, as its own value: it is a separate choice from the agreement to
use the service and is false unless the person makes it (handoff: no automatic training consent). Sessions that
exist get false.

Revision ID: 0021
Revises: 0020
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sessions ADD COLUMN training_consent boolean NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE sessions DROP COLUMN training_consent")
