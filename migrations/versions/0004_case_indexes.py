"""Indexes for imported cases: profile-cluster membership (split manifests, leakage checks),
original split and label lookups.

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX dataset_cases_cluster_idx ON dataset_cases(profile_cluster_id)")
    op.execute("CREATE INDEX dataset_cases_split_idx ON dataset_cases(source_split) WHERE source_split IS NOT NULL")
    op.execute("CREATE INDEX case_labels_disease_idx ON case_labels(disease_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS case_labels_disease_idx")
    op.execute("DROP INDEX IF EXISTS dataset_cases_split_idx")
    op.execute("DROP INDEX IF EXISTS dataset_cases_cluster_idx")
