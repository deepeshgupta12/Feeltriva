"""Registry of the raw source archives held in private object storage.

One row per archive: its SHA-256, where the unchanged bytes are stored, and when that stored
copy was last re-read and verified. Source records keep their logical locator
(`zip://<archive>#<member>:row=N`); this table resolves the archive name to the stored object.
The application role gets no access: serving never needs the raw archives.

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE source_archives (
            archive_name text PRIMARY KEY,
            sha256 text NOT NULL UNIQUE,
            size_bytes bigint NOT NULL CHECK (size_bytes > 0),
            bucket text NOT NULL,
            object_key text NOT NULL,
            version_id text,
            object_uri text NOT NULL,
            stored_at timestamptz NOT NULL DEFAULT now(),
            verified_at timestamptz
        )"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS source_archives")
