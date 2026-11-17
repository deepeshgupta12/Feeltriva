"""Runs against the six supplied archives in data/raw (skipped when they are absent)."""

from __future__ import annotations

import os

import pytest
from feeltriva_ingestion.archives import load_manifest, verify_all
from feeltriva_ingestion.audit import compare, run_audit

pytestmark = pytest.mark.archives


def test_archives_match_manifest_checksums_and_pass_safety_checks():
    entries = verify_all()
    assert sorted(entries) == [f"archive({i}).zip" for i in range(11, 17)]
    assert sum(len(v) for v in entries.values()) == 97  # 12 CSV + 85 text files


def test_audit_reproduces_the_handoff_measurements():
    result = run_audit()
    assert compare(result) == []
    assert len(result["files"]) == 12 and len(result["text_files"]) == 85
    assert result["union_lexical_disease_labels"] == 960
    assert result["archive15_train_test_shared_profiles_excluding_patient_id"] == 27622
    by_file = {f["file"]: f for f in result["files"]}
    a16 = by_file["unified_820_diseases_symptoms_dataset_ROWLEVEL_CLEANED.csv"]
    assert a16["duplicate_header_count"] == 37
    assert all(n > 0 for n in a16["duplicate_column_disagreement_rows"].values())
    assert len(a16["duplicate_column_disagreement_rows"]) == 37  # every repeated name has a real conflict
    assert by_file["data.csv"]["exact_duplicate_rows"] == 57305
    assert by_file["final_symptoms_to_disease.csv"]["exact_duplicate_rows"] == 28988
    assert sum(f["malformed_rows"] for f in result["files"]) == 0


@pytest.mark.postgres
def test_reference_load_is_idempotent_and_everything_is_pending(owner_db):
    from feeltriva_api.models import (
        Disease,
        DiseaseMapping,
        FeatureMapping,
        Source,
        SourceRecord,
        Statement,
        StatementSource,
    )
    from feeltriva_ingestion.load import load_reference, source_id
    from sqlalchemy import func, select

    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    load_reference(database_url=url)
    second = load_reference(database_url=url)
    assert all(inserted == 0 for inserted, _ in second.values()), second  # rerun changes nothing

    # The test database persists and other tests add their own synthetic rows (with the same ID
    # prefixes, because they use the same ID functions), so count only what belongs to the sources
    # this loader registers.
    manifest = load_manifest()
    real = [source_id(f["archive"], f["file"]) for f in manifest.files] + [source_id("archive(13).zip", "*.txt")]
    records = select(SourceRecord.record_id).where(SourceRecord.source_id.in_(real))
    loaded = {
        Source: Source.source_id.in_(real),
        SourceRecord: SourceRecord.source_id.in_(real),
        Disease: Disease.disease_id.in_(select(DiseaseMapping.disease_id).where(DiseaseMapping.source_id.in_(real))),
        DiseaseMapping: DiseaseMapping.source_id.in_(real),
        FeatureMapping: FeatureMapping.source_id.in_(real),
        Statement: Statement.statement_id.in_(
            select(StatementSource.statement_id).where(StatementSource.record_id.in_(records))
        ),
        StatementSource: StatementSource.record_id.in_(records),
    }
    with owner_db.transaction(None) as tx:

        def scoped(model):
            return loaded[model]

        totals = {
            m.__tablename__: tx.execute(select(func.count()).select_from(m).where(scoped(m))).scalar_one()
            for m in loaded
        }
        assert totals == {
            "sources": 13,
            "source_records": 85 + 714 + 712 + 621 + 820 + len(manifest.text_files),
            "diseases": 960,
            "disease_mappings": 3117,
            "feature_mappings": 1651,
            "statements": 85 + 714 + 712 + 621 + 820,
            "statement_sources": 85 + 714 + 712 + 621 + 820,
        }
        for model in (Disease, DiseaseMapping, FeatureMapping, Statement):
            not_pending = tx.execute(
                select(func.count()).select_from(model).where(scoped(model), model.status != "pending")
            ).scalar_one()
            assert not_pending == 0, model.__tablename__
        by_type = dict(
            tx.execute(
                select(Statement.statement_type, func.count())
                .where(scoped(Statement))
                .group_by(Statement.statement_type)
            ).all()
        )
        assert by_type == {"description": 85 + 820, "cause": 714, "symptom": 712, "treatment": 621}
        repeated = [
            m
            for m in tx.execute(select(FeatureMapping).where(scoped(FeatureMapping))).scalars()
            if (m.transformation or {}).get("repeated_header")
        ]
        assert len(repeated) == 74 and len({m.original_term for m in repeated}) == 37
        assert all(m.transformation["disagreement_rows"] > 0 for m in repeated)  # conflicts retained per position
        assert len({(m.source_id, m.column_index) for m in repeated}) == 74
