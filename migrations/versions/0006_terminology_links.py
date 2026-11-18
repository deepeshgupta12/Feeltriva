"""Candidate links from our disease and feature candidates to standard vocabularies (M2.11).

One row per candidate link to a code of ICD-11 or LOINC. A row keeps the code, its title and its
URI together (the WHO licence requires all three wherever ICD is stored), the release it came
from, how the match was found, and a review status. Rows are candidates: `pending` until a
reviewer decides. The application role gets no access; serving does not read candidates.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE terminology_links (
            link_id text PRIMARY KEY,
            disease_id text REFERENCES diseases,
            feature_id text REFERENCES features,
            system text NOT NULL,
            system_version text NOT NULL,
            code text NOT NULL,
            title text NOT NULL,
            uri text,
            match_method text NOT NULL,
            detail jsonb NOT NULL DEFAULT '{}',
            status review_state NOT NULL DEFAULT 'pending',
            reviewer text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK ((disease_id IS NULL) <> (feature_id IS NULL))
        )"""
    )
    op.execute("CREATE INDEX terminology_links_disease ON terminology_links (disease_id) WHERE disease_id IS NOT NULL")
    op.execute("CREATE INDEX terminology_links_feature ON terminology_links (feature_id) WHERE feature_id IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS terminology_links")
