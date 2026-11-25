"""Names without a link, and the terms a reviewer could confirm for them (M2.4b).

The look-ups of M2.11, M2.14 and M2.16 store a link only for an exact name, or for the one
identifier a vocabulary marks equivalent. Everything else went to review files outside the
database, where no screen could read it and no decision could be recorded. This table holds it:

- the close ICD-11 search results (best score 0.9 or more, no entity with exactly our name);
- for each name without an HPO or MONDO link, the reason, and one row per near term;
- for a label whose MONDO term lists several SNOMED CT or ICD-11 identifiers as equivalent, one row
  per identifier.

A row is a proposal, not a link (decision E56): nothing in it is used anywhere. When a reviewer
confirms a row that names a term, the link is made in `terminology_links`, approved under that
reviewer's name; `link_id` is the ID that link has. A row without a term records only why a name
has no link.

The rows hold codes of outside vocabularies, so only a reviewer's transaction can read them (E63).
The application role may change `status` and `reviewer`, and may now add a row to
`terminology_links`, both only inside a reviewer's transaction.

Revision ID: 0019
Revises: 0018
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

APP = "feeltriva_app"
IS_REVIEWER = "current_setting('app.role', true) = 'reviewer'"


def upgrade() -> None:
    op.execute(
        """CREATE TABLE link_proposals (
            proposal_id text PRIMARY KEY,
            disease_id text REFERENCES diseases,
            feature_id text REFERENCES features,
            system text NOT NULL,
            system_version text NOT NULL,
            basis text NOT NULL,
            reason text NOT NULL,
            code text,
            title text,
            uri text,
            link_id text,
            detail jsonb NOT NULL DEFAULT '{}',
            status review_state NOT NULL DEFAULT 'pending',
            reviewer text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK ((disease_id IS NULL) <> (feature_id IS NULL)),
            CHECK ((code IS NULL) = (title IS NULL) AND (code IS NULL) = (uri IS NULL)
                   AND (code IS NULL) = (link_id IS NULL))
        )"""
    )
    op.execute("CREATE INDEX link_proposals_disease ON link_proposals (disease_id) WHERE disease_id IS NOT NULL")
    op.execute("CREATE INDEX link_proposals_feature ON link_proposals (feature_id) WHERE feature_id IS NOT NULL")
    op.execute("CREATE INDEX link_proposals_basis ON link_proposals (basis, status)")
    op.execute(f"GRANT SELECT ON link_proposals TO {APP}")
    op.execute(f"GRANT UPDATE (status, reviewer) ON link_proposals TO {APP}")
    op.execute("ALTER TABLE link_proposals ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY link_proposals_read ON link_proposals FOR SELECT USING ({IS_REVIEWER})")
    op.execute(
        f"CREATE POLICY link_proposals_review ON link_proposals FOR UPDATE USING ({IS_REVIEWER}) "
        f"WITH CHECK ({IS_REVIEWER})"
    )
    # A confirmed proposal makes its link: the application role may add one, inside a reviewer's transaction only.
    op.execute(f"GRANT INSERT ON terminology_links TO {APP}")
    op.execute(f"CREATE POLICY terminology_links_add ON terminology_links FOR INSERT WITH CHECK ({IS_REVIEWER})")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS terminology_links_add ON terminology_links")
    op.execute(f"REVOKE INSERT ON terminology_links FROM {APP}")
    op.execute("DROP TABLE IF EXISTS link_proposals")
