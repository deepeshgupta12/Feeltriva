"""Invented rows for the browser test of the review workspace (`pnpm e2e:review`).

Writes into the database named by TEST_MIGRATION_DATABASE_URL, which must be a test database:
the browser test records notes and decisions, and those must never land in real data. Prints
the tag of the rows it made; the browser test finds its rows by that tag.

Run from the repository root:  uv run python apps/web/scripts/seed_review_e2e.py
"""

from __future__ import annotations

import os
import sys
import uuid

from feeltriva_api.db import Database
from feeltriva_api.models import (
    Disease,
    Feature,
    FeatureMapping,
    LinkProposal,
    MappingRelease,
    Source,
    SourceRecord,
    Statement,
    StatementClaim,
    StatementSource,
    TerminologyLink,
)

SENTENCE = "Signs include a pretend hat, a scarf and a coat."


def main() -> int:
    url = os.environ.get("TEST_MIGRATION_DATABASE_URL", "")
    if not url or "test" not in url.rsplit("/", 1)[-1]:
        print("TEST_MIGRATION_DATABASE_URL must name a test database", file=sys.stderr)
        return 1
    tag = uuid.uuid4().hex[:10]
    with Database(url).transaction(None, role="migration") as tx:
        tx.add(MappingRelease(release_id=f"e2e-map-{tag}", version=f"e2e-map-{tag}-0"))
        tx.add(Source(source_id=f"e2e_src_{tag}", source_name=f"e2e-{tag}.csv", version="1", sha256=f"e2e-{tag}"))
        tx.add(Disease(disease_id=f"e2e_dis_{tag}", preferred_name=f"pretend ache {tag}"))
        tx.add(Feature(feature_id=f"e2e_feat_{tag}", preferred_name=f"hat {tag}", kind="symptom", value_type="boolean"))
        # M2.4h: an approved item, so that the list of names of this run can be published.
        tx.add(
            Feature(
                feature_id=f"e2e_pub_{tag}",
                preferred_name=f"scarf {tag}",
                kind="symptom",
                value_type="boolean",
                status="approved",
            )
        )
        tx.flush()
        for column in (3, 9):  # one heading at two column positions that disagree in 12 rows
            tx.add(
                FeatureMapping(
                    mapping_id=f"e2e_fm_{tag}_{column}",
                    release_id=f"e2e-map-{tag}",
                    source_id=f"e2e_src_{tag}",
                    file_path="e2e.csv",
                    column_index=column,
                    original_term=f"itching {tag}",
                    feature_id=f"e2e_feat_{tag}",
                    transformation={"repeated_header": True, "repeated_positions": [3, 9], "disagreement_rows": 12},
                )
            )
        for key, code, title, method in (
            ("general", f"ZZ{tag}", f"Pretend ache {tag}", "exact_title"),
            ("narrow", f"ZZ{tag}.0", f"Pretend ache of the left side {tag}", "exact_synonym"),
        ):
            tx.add(
                TerminologyLink(
                    link_id=f"e2e_tl_{tag}_{key}",
                    disease_id=f"e2e_dis_{tag}",
                    system="ICD-11 MMS",
                    system_version="e2e",
                    code=code,
                    title=title,
                    uri=f"http://example.invalid/{code}",
                    match_method=method,
                    detail={},
                )
            )
        tx.add(
            SourceRecord(
                record_id=f"e2e_rec_{tag}",
                source_id=f"e2e_src_{tag}",
                file_path="symptoms.csv",
                row_number=1,
                content_hash=f"e2e-{tag}",
                raw_object_uri=f"test://e2e/{tag}",
            )
        )
        tx.add(
            Statement(
                statement_id=f"e2e_st_{tag}",
                disease_id=f"e2e_dis_{tag}",
                statement_type="symptom",
                text_content=SENTENCE,
            )
        )
        tx.flush()
        tx.add(StatementSource(statement_id=f"e2e_st_{tag}", record_id=f"e2e_rec_{tag}"))
        tx.add(
            StatementClaim(
                claim_id=f"e2e_cl_{tag}_s",
                statement_id=f"e2e_st_{tag}",
                kind="sentence",
                span_start=0,
                span_end=len(SENTENCE),
                claim_text=SENTENCE,
                rule="e2e:sentence",
                cues={},
            )
        )
        tx.flush()
        start = SENTENCE.index("a pretend hat")
        tx.add(
            StatementClaim(
                claim_id=f"e2e_cl_{tag}_hat",
                statement_id=f"e2e_st_{tag}",
                parent_claim_id=f"e2e_cl_{tag}_s",
                kind="list_item",
                span_start=start,
                span_end=start + len("a pretend hat"),
                claim_text="a pretend hat",
                rule="e2e:enumeration",
                cues={"first_item_preposition": ["of"]},
                proposed_feature_id=f"e2e_feat_{tag}",
            )
        )
        # M2.4b: two close search results, each for its own invented condition, and one name without a suggestion.
        for key, name in (("near", "pretend chill"), ("far", "pretend shiver")):
            tx.add(Disease(disease_id=f"e2e_dis_{tag}_{key}", preferred_name=f"{name} {tag}"))
        tx.flush()
        for key, code, title, score in (
            ("near", f"YY{tag}.1", f"Pretend chilling {tag}", 0.96),
            ("far", f"YY{tag}.2", f"Pretend shaking {tag}", 0.91),
        ):
            tx.add(
                LinkProposal(
                    proposal_id=f"e2e_lp_{tag}_{key}",
                    disease_id=f"e2e_dis_{tag}_{key}",
                    system="ICD-11 MMS",
                    system_version="e2e",
                    basis="close_search_result",
                    reason="no ICD-11 entity carries exactly this name; this is the best result of the name search",
                    code=code,
                    title=title,
                    uri=f"http://example.invalid/{code}",
                    link_id=f"e2e_tl_{tag}_{key}",
                    detail={"score": score},
                )
            )
        tx.add(
            LinkProposal(
                proposal_id=f"e2e_lp_{tag}_none",
                feature_id=f"e2e_feat_{tag}",
                system="HPO",
                system_version="e2e",
                basis="no_term_near",
                reason="no term carries this name or shares half of its words",
                detail={},
            )
        )
    print(tag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
