"""Initial relational schema, translated statement-for-statement from specs/schema.sql.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

STATEMENTS = [
    """
CREATE TYPE review_state AS ENUM ('pending','approved','rejected','retired')
    """,
    """
CREATE TYPE feature_kind AS ENUM ('symptom','sign','history','risk_factor','measurement','other')
    """,
    """
CREATE TYPE presence_state AS ENUM ('present','absent','uncertain','not_asked')
    """,
    """
CREATE TABLE sources (
 source_id text PRIMARY KEY, source_name text NOT NULL, version text NOT NULL,
 origin_url text, licence text, permitted_uses jsonb NOT NULL DEFAULT '{}',
 population jsonb NOT NULL DEFAULT '{}', provenance_status review_state NOT NULL DEFAULT 'pending',
 sha256 text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(source_name,version)
)
    """,
    """
CREATE TABLE source_records (
 record_id text PRIMARY KEY, source_id text NOT NULL REFERENCES sources,
 file_path text NOT NULL, row_number bigint, content_hash text NOT NULL,
 raw_object_uri text NOT NULL, original_split text, quality_flags jsonb NOT NULL DEFAULT '[]',
 UNIQUE(source_id,file_path,row_number)
)
    """,
    """
CREATE INDEX source_records_hash_idx ON source_records(content_hash)
    """,
    """
CREATE TABLE mapping_releases (release_id text PRIMARY KEY, version text UNIQUE NOT NULL, status review_state NOT NULL DEFAULT 'pending', approved_by text, approved_at timestamptz)
    """,
    """
CREATE TABLE diseases (
 disease_id text PRIMARY KEY, preferred_name text NOT NULL, definition text,
 status review_state NOT NULL DEFAULT 'pending', redirected_to text REFERENCES diseases,
 external_ids jsonb NOT NULL DEFAULT '{}', CHECK(redirected_to IS NULL OR redirected_to<>disease_id)
)
    """,
    """
CREATE TABLE disease_mappings (
 mapping_id text PRIMARY KEY, release_id text NOT NULL REFERENCES mapping_releases,
 source_id text NOT NULL REFERENCES sources, original_label text NOT NULL, original_id text,
 disease_id text REFERENCES diseases, method text NOT NULL, status review_state NOT NULL DEFAULT 'pending',
 reviewer text, UNIQUE(release_id,source_id,original_label)
)
    """,
    """
CREATE TABLE features (
 feature_id text PRIMARY KEY, preferred_name text NOT NULL, kind feature_kind NOT NULL,
 value_type text NOT NULL CHECK(value_type IN ('boolean','number','category','text')),
 unit text, aliases jsonb NOT NULL DEFAULT '[]', status review_state NOT NULL DEFAULT 'pending'
)
    """,
    """
CREATE TABLE feature_mappings (
 mapping_id text PRIMARY KEY, release_id text NOT NULL REFERENCES mapping_releases,
 source_id text NOT NULL REFERENCES sources, file_path text NOT NULL, column_index integer,
 original_term text NOT NULL, feature_id text REFERENCES features, zero_semantics text NOT NULL DEFAULT 'unknown',
 transformation jsonb NOT NULL DEFAULT '{}', status review_state NOT NULL DEFAULT 'pending',
 UNIQUE(release_id,source_id,file_path,column_index)
)
    """,
    """
CREATE TABLE statements (
 statement_id text PRIMARY KEY, disease_id text REFERENCES diseases,
 statement_type text NOT NULL CHECK(statement_type IN ('description','symptom','treatment','management','prevention','cause')),
 text_content text NOT NULL, applicability jsonb NOT NULL DEFAULT '{}',
 status review_state NOT NULL DEFAULT 'pending', reviewed_by text, reviewed_at timestamptz, expires_at timestamptz
)
    """,
    """
CREATE TABLE statement_sources (
 statement_id text REFERENCES statements, record_id text REFERENCES source_records,
 source_url text, text_span jsonb, PRIMARY KEY(statement_id,record_id)
)
    """,
    """
CREATE TABLE disease_feature_evidence (
 evidence_id text PRIMARY KEY, disease_id text NOT NULL REFERENCES diseases, feature_id text NOT NULL REFERENCES features,
 statement_id text REFERENCES statements, record_id text REFERENCES source_records,
 relationship text NOT NULL, context jsonb NOT NULL DEFAULT '{}',
 frequency numeric CHECK(frequency IS NULL OR frequency BETWEEN 0 AND 1), frequency_denominator bigint,
 evidence_type text NOT NULL, status review_state NOT NULL DEFAULT 'pending',
 CHECK(statement_id IS NOT NULL OR record_id IS NOT NULL)
)
    """,
    """
CREATE TABLE dataset_cases (
 case_id text PRIMARY KEY, record_id text UNIQUE NOT NULL REFERENCES source_records,
 source_patient_id text, source_split text, age_value numeric, age_unit text,
 original_demographic_field text, original_demographic_value text,
 profile_cluster_id text, duplicate_status text NOT NULL DEFAULT 'unreviewed',
 CHECK(age_value IS NULL OR age_value>=0)
)
    """,
    """
CREATE TABLE case_labels (
 case_id text REFERENCES dataset_cases, disease_id text REFERENCES diseases,
 original_label text NOT NULL, label_origin text NOT NULL DEFAULT 'unknown',
 PRIMARY KEY(case_id,disease_id,original_label)
)
    """,
    """
CREATE TABLE case_features (
 case_id text REFERENCES dataset_cases, mapping_id text REFERENCES feature_mappings,
 raw_value text, normalized_value jsonb, presence presence_state NOT NULL DEFAULT 'uncertain',
 conflict boolean NOT NULL DEFAULT false, PRIMARY KEY(case_id,mapping_id)
)
    """,
    """
CREATE TABLE knowledge_releases (release_id text PRIMARY KEY, mapping_release_id text REFERENCES mapping_releases, version text UNIQUE NOT NULL, manifest_uri text NOT NULL, status review_state NOT NULL DEFAULT 'pending')
    """,
    """
CREATE TABLE evidence_chunks (
 chunk_id text PRIMARY KEY, statement_id text REFERENCES statements, record_id text REFERENCES source_records,
 knowledge_release_id text NOT NULL REFERENCES knowledge_releases, chunk_text text NOT NULL,
 search_vector tsvector, metadata jsonb NOT NULL DEFAULT '{}',
 CHECK(statement_id IS NOT NULL OR record_id IS NOT NULL)
)
    """,
    """
CREATE INDEX evidence_chunks_search_idx ON evidence_chunks USING gin(search_vector)
    """,
    """
CREATE TABLE rule_bundles (
 bundle_id text PRIMARY KEY, version text UNIQUE NOT NULL, status review_state NOT NULL DEFAULT 'pending',
 manifest_uri text NOT NULL, approved_by text, approved_at timestamptz
)
    """,
    """
CREATE TABLE clinical_rules (
 rule_id text PRIMARY KEY, bundle_id text NOT NULL REFERENCES rule_bundles,
 rule_type text NOT NULL, applicability jsonb NOT NULL, condition_ast jsonb NOT NULL,
 action jsonb NOT NULL, evidence_ids jsonb NOT NULL, priority integer NOT NULL,
 status review_state NOT NULL DEFAULT 'pending'
)
    """,
    """
CREATE TABLE followup_questions (
 question_id text PRIMARY KEY, bundle_id text NOT NULL REFERENCES rule_bundles,
 feature_id text REFERENCES features, wording text NOT NULL, answer_schema jsonb NOT NULL,
 applicability jsonb NOT NULL, branch_rules jsonb NOT NULL, evidence_ids jsonb NOT NULL,
 status review_state NOT NULL DEFAULT 'pending'
)
    """,
    """
CREATE TABLE sessions (
 session_id uuid PRIMARY KEY, owner_subject text NOT NULL, state text NOT NULL,
 observation_version bigint NOT NULL DEFAULT 0, consent_version text NOT NULL,
 demographics jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL, deleted_at timestamptz
)
    """,
    """
CREATE TABLE session_messages (
 message_id uuid PRIMARY KEY, session_id uuid NOT NULL REFERENCES sessions ON DELETE CASCADE,
 role text NOT NULL CHECK(role IN ('user','assistant')), encrypted_content bytea NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
)
    """,
    """
CREATE TABLE session_observations (
 observation_id uuid PRIMARY KEY, session_id uuid NOT NULL REFERENCES sessions ON DELETE CASCADE,
 message_id uuid REFERENCES session_messages ON DELETE SET NULL, feature_id text REFERENCES features,
 raw_phrase_encrypted bytea, presence presence_state NOT NULL, value jsonb,
 modifiers jsonb NOT NULL DEFAULT '{}', confirmed boolean NOT NULL DEFAULT false,
 observation_version bigint NOT NULL, supersedes uuid REFERENCES session_observations,
 created_at timestamptz NOT NULL DEFAULT now()
)
    """,
    """
CREATE TABLE session_answers (
 answer_id uuid PRIMARY KEY, session_id uuid NOT NULL REFERENCES sessions ON DELETE CASCADE,
 question_id text NOT NULL REFERENCES followup_questions, value jsonb NOT NULL,
 observation_version bigint NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
)
    """,
    """
CREATE TABLE model_releases (
 model_release_id text PRIMARY KEY, version text UNIQUE NOT NULL, artifact_uri text NOT NULL,
 dataset_manifest_uri text NOT NULL, metrics_uri text NOT NULL, allowed_scope jsonb NOT NULL,
 status review_state NOT NULL DEFAULT 'pending'
)
    """,
    """
CREATE TABLE assessments (
 assessment_id uuid PRIMARY KEY, session_id uuid NOT NULL REFERENCES sessions ON DELETE CASCADE,
 observation_version bigint NOT NULL, status text NOT NULL, urgency text NOT NULL,
 candidates jsonb NOT NULL DEFAULT '[]', unknowns jsonb NOT NULL DEFAULT '[]',
 evidence_ids jsonb NOT NULL DEFAULT '[]', model_release_id text REFERENCES model_releases,
 knowledge_release_id text REFERENCES knowledge_releases, rule_bundle_id text REFERENCES rule_bundles,
 prompt_version text NOT NULL, provider_model_id text, next_action jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
)
    """,
    """
CREATE TABLE assessment_feedback (
 feedback_id uuid PRIMARY KEY, assessment_id uuid NOT NULL REFERENCES assessments ON DELETE CASCADE,
 origin text NOT NULL CHECK(origin IN ('user','clinician','reviewer')), outcome jsonb NOT NULL,
 clinically_verified boolean NOT NULL DEFAULT false, training_consent boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now()
)
    """,
    """
CREATE TABLE audit_events (
 event_id uuid PRIMARY KEY, session_id uuid REFERENCES sessions ON DELETE SET NULL,
 actor_subject text NOT NULL, event_type text NOT NULL, redacted_metadata jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now()
)
    """,
    """
CREATE TABLE idempotency_keys (
 owner_subject text NOT NULL, key text NOT NULL, request_hash text NOT NULL,
 operation text NOT NULL, session_id uuid REFERENCES sessions ON DELETE CASCADE,
 response_status integer, encrypted_response bytea,
 state text NOT NULL CHECK(state IN ('in_progress','completed','failed')),
 expires_at timestamptz NOT NULL,
 PRIMARY KEY(owner_subject,key)
)
    """,
]

TABLES = ['sources', 'source_records', 'mapping_releases', 'diseases', 'disease_mappings', 'features', 'feature_mappings', 'statements', 'statement_sources', 'disease_feature_evidence', 'dataset_cases', 'case_labels', 'case_features', 'knowledge_releases', 'evidence_chunks', 'rule_bundles', 'clinical_rules', 'followup_questions', 'sessions', 'session_messages', 'session_observations', 'session_answers', 'model_releases', 'assessments', 'assessment_feedback', 'audit_events', 'idempotency_keys']
TYPES = ['review_state', 'feature_kind', 'presence_state']


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for name in reversed(TYPES):
        op.execute(f"DROP TYPE IF EXISTS {name}")
