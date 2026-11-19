"""Answers to the questions that are not yes/no, taken from the source release (M2.13a).

Archive 15 renders every question as 0 or 1. For a question with several possible answers the 1
says only that an answer was recorded; the answer itself is in the release the file was derived
from. One row here is one answer of one case to one question, written as the release writes it
(a value code such as `V_112`, or a number), with the release split and row it was read from.

The archive's own value stays where it is, in `case_features`. Import-only: the application
role gets no access.

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE case_answers (
            case_id text NOT NULL REFERENCES dataset_cases,
            mapping_id text NOT NULL REFERENCES feature_mappings,
            answer text NOT NULL,
            source_id text NOT NULL REFERENCES sources,
            release_split text NOT NULL,
            release_row integer NOT NULL CHECK (release_row > 0),
            PRIMARY KEY (case_id, mapping_id, answer)
        )"""
    )
    op.execute("CREATE INDEX case_answers_mapping ON case_answers (mapping_id, answer)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS case_answers")
