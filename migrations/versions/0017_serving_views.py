"""Serving views: what may be shown, read from the current releases (M2.9).

Four views. Serving code reads these and nothing else of the reviewed knowledge.

- `reviewed_disease_catalog`: the diseases of the current mapping release, with their names,
  definitions, other names and the labels merged into them.
- `reviewed_condition_statements`: the statements of the current knowledge release, each under
  the disease it stands under, with the source records it rests on.
- `reviewed_care_statements`: of those, the statements about care (treatment, management,
  prevention).
- `reviewed_disease_feature_edges`: the links between a disease and a feature of the current
  knowledge release.

A row is in a view only when all of this holds at the moment of reading:

- it is in the current release (a published release changes only by a new release or a rollback);
- the knowledge release is pinned to the mapping release that is current, otherwise the three
  knowledge views are empty;
- the row is still approved in the working tables: a statement, evidence row, disease or feature
  that a reviewer has since rejected or retired drops out at once, without a new release;
- its source is still approved (rights): a statement keeps the attributions whose source is
  approved and drops out when none is left;
- a statement has not expired.

So a pending, rejected, retired or expired row never appears, and neither does anything that was
not published. The views are read with the rights of their owner; the application role may only
select from them.

Revision ID: 0017
Revises: 0016
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

APP = "feeltriva_app"
VIEWS = (
    "reviewed_disease_catalog",
    "reviewed_condition_statements",
    "reviewed_care_statements",
    "reviewed_disease_feature_edges",
)
# The knowledge release that is current, and only while the mapping release it was published against is current.
KNOWLEDGE = """published_knowledge k
               JOIN published_mappings m ON m.release_id = k.mapping_release AND m.is_current"""


def upgrade() -> None:
    op.execute(
        """CREATE VIEW reviewed_disease_catalog AS
           SELECT m.release_id AS mapping_release, c.disease_id, c.preferred_name AS name, c.definition,
                  c.synonyms AS aliases, c.merged_labels
           FROM published_mappings m
           CROSS JOIN LATERAL jsonb_to_recordset(m.content -> 'diseases')
                AS c(disease_id text, preferred_name text, definition text, synonyms jsonb, merged_labels jsonb)
           JOIN diseases d ON d.disease_id = c.disease_id AND d.status = 'approved' AND d.redirected_to IS NULL
           WHERE m.is_current"""
    )
    op.execute(
        f"""CREATE VIEW reviewed_condition_statements AS
           SELECT k.release_id AS knowledge_release, cat.disease_id, s.statement_id, s.statement_type, s.text,
                  s.applicability, live.expires_at, rights.sources
           FROM {KNOWLEDGE}
           CROSS JOIN LATERAL jsonb_to_recordset(k.content -> 'statements')
                AS s(statement_id text, resolves_to text, statement_type text, text text, applicability jsonb,
                     sources jsonb)
           JOIN reviewed_disease_catalog cat ON cat.disease_id = s.resolves_to
           JOIN statements live ON live.statement_id = s.statement_id AND live.status = 'approved'
           CROSS JOIN LATERAL (
               SELECT jsonb_agg(
                          jsonb_build_object('record_id', x ->> 'record_id', 'source_id', x ->> 'source_id',
                                             'source_url', x ->> 'source_url')
                          ORDER BY x ->> 'record_id') AS sources
               FROM jsonb_array_elements(s.sources) x
               JOIN sources src ON src.source_id = x ->> 'source_id' AND src.provenance_status = 'approved'
           ) rights
           WHERE k.is_current AND rights.sources IS NOT NULL
             AND (live.expires_at IS NULL OR live.expires_at > now())"""
    )
    op.execute(
        """CREATE VIEW reviewed_care_statements AS
           SELECT * FROM reviewed_condition_statements
           WHERE statement_type IN ('treatment', 'management', 'prevention')"""
    )
    op.execute(
        f"""CREATE VIEW reviewed_disease_feature_edges AS
           SELECT k.release_id AS knowledge_release, cat.disease_id, e.feature_id, e.relationship, e.evidence_type,
                  e.context, e.frequency, e.frequency_denominator, e.evidence_id, e.statement_id, e.record_id,
                  e.source_id
           FROM {KNOWLEDGE}
           CROSS JOIN LATERAL jsonb_to_recordset(k.content -> 'evidence')
                AS e(evidence_id text, resolves_to text, feature_id text, relationship text, evidence_type text,
                     context jsonb, frequency numeric, frequency_denominator bigint, statement_id text,
                     record_id text, source_id text)
           JOIN reviewed_disease_catalog cat ON cat.disease_id = e.resolves_to
           JOIN features f ON f.feature_id = e.feature_id AND f.status = 'approved'
           JOIN disease_feature_evidence live ON live.evidence_id = e.evidence_id AND live.status = 'approved'
           WHERE k.is_current
             AND (e.source_id IS NULL OR EXISTS (
                     SELECT 1 FROM sources src
                     WHERE src.source_id = e.source_id AND src.provenance_status = 'approved'))
             AND (e.statement_id IS NULL OR EXISTS (
                     SELECT 1 FROM reviewed_condition_statements st WHERE st.statement_id = e.statement_id))"""
    )
    for view in VIEWS:
        op.execute(f"GRANT SELECT ON {view} TO {APP}")


def downgrade() -> None:
    for view in reversed(VIEWS):
        op.execute(f"DROP VIEW {view}")
