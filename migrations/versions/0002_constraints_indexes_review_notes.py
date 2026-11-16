"""Constraints and indexes justified by the service's query patterns; reviewer notes.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UP = [
    # State machine and enumerations enforced in the database as well as the service.
    """ALTER TABLE sessions ADD CONSTRAINT sessions_state_check CHECK (state IN (
        'intake','clarifying','assessing','result_ready','urgent_handoff','out_of_scope',
        'insufficient_information','system_unavailable','closed'))""",
    "ALTER TABLE sessions ADD CONSTRAINT sessions_version_check CHECK (observation_version >= 0)",
    """ALTER TABLE assessments ADD CONSTRAINT assessments_status_check CHECK (status IN (
        'needs_clarification','provisional','urgent_handoff','out_of_scope',
        'insufficient_information','system_unavailable'))""",
    """ALTER TABLE assessments ADD CONSTRAINT assessments_urgency_check CHECK (urgency IN (
        'not_assessed','emergency','urgent','routine','self_care_with_safety_net'))""",
    """ALTER TABLE session_observations ADD CONSTRAINT session_observations_no_self_supersede
        CHECK (supersedes IS NULL OR supersedes <> observation_id)""",
    # An observation can be superseded at most once: corrections form a chain, not a fork.
    """CREATE UNIQUE INDEX session_observations_supersedes_uidx ON session_observations(supersedes)
        WHERE supersedes IS NOT NULL""",
    # Every owner-scoped read starts from (owner, session); children are read by session.
    "CREATE INDEX sessions_owner_idx ON sessions(owner_subject) WHERE deleted_at IS NULL",
    "CREATE INDEX session_observations_session_idx ON session_observations(session_id, observation_version)",
    "CREATE INDEX session_messages_session_idx ON session_messages(session_id)",
    "CREATE INDEX session_answers_session_idx ON session_answers(session_id, observation_version)",
    "CREATE INDEX assessments_session_idx ON assessments(session_id, observation_version DESC)",
    "CREATE INDEX audit_events_session_idx ON audit_events(session_id)",
    "CREATE INDEX idempotency_keys_session_idx ON idempotency_keys(session_id)",
    "CREATE INDEX idempotency_keys_expiry_idx ON idempotency_keys(expires_at)",
    # Review workspace filters.
    "CREATE INDEX disease_mappings_disease_idx ON disease_mappings(disease_id)",
    "CREATE INDEX disease_mappings_status_idx ON disease_mappings(status)",
    "CREATE INDEX feature_mappings_feature_idx ON feature_mappings(feature_id)",
    "CREATE INDEX statements_disease_status_idx ON statements(disease_id, status)",
    """CREATE TABLE review_notes (
        note_id uuid PRIMARY KEY, target_type text NOT NULL, target_id text NOT NULL,
        reviewer text NOT NULL, note text NOT NULL, status_change text,
        created_at timestamptz NOT NULL DEFAULT now())""",
    "CREATE INDEX review_notes_target_idx ON review_notes(target_type, target_id)",
]

DOWN = [
    "DROP TABLE IF EXISTS review_notes",
    "DROP INDEX IF EXISTS statements_disease_status_idx",
    "DROP INDEX IF EXISTS feature_mappings_feature_idx",
    "DROP INDEX IF EXISTS disease_mappings_status_idx",
    "DROP INDEX IF EXISTS disease_mappings_disease_idx",
    "DROP INDEX IF EXISTS idempotency_keys_expiry_idx",
    "DROP INDEX IF EXISTS idempotency_keys_session_idx",
    "DROP INDEX IF EXISTS audit_events_session_idx",
    "DROP INDEX IF EXISTS assessments_session_idx",
    "DROP INDEX IF EXISTS session_answers_session_idx",
    "DROP INDEX IF EXISTS session_messages_session_idx",
    "DROP INDEX IF EXISTS session_observations_session_idx",
    "DROP INDEX IF EXISTS sessions_owner_idx",
    "DROP INDEX IF EXISTS session_observations_supersedes_uidx",
    "ALTER TABLE session_observations DROP CONSTRAINT IF EXISTS session_observations_no_self_supersede",
    "ALTER TABLE assessments DROP CONSTRAINT IF EXISTS assessments_urgency_check",
    "ALTER TABLE assessments DROP CONSTRAINT IF EXISTS assessments_status_check",
    "ALTER TABLE sessions DROP CONSTRAINT IF EXISTS sessions_version_check",
    "ALTER TABLE sessions DROP CONSTRAINT IF EXISTS sessions_state_check",
]


def upgrade() -> None:
    for statement in UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWN:
        op.execute(statement)
