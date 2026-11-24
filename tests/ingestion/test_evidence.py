"""Proposed disease-feature evidence: narrative mentions and per-source co-occurrence."""

from __future__ import annotations

import os
import re
import uuid
import zipfile

import pytest
from feeltriva_api.models import (
    Disease,
    Feature,
    FeatureMapping,
    MappingRelease,
    Source,
    SourceRecord,
    Statement,
    StatementSource,
)
from feeltriva_ingestion.archives import Manifest, sha256_file
from feeltriva_ingestion.cases import load_cases
from feeltriva_ingestion.evidence import (
    COOCCURRENCE_TYPE,
    NARRATIVE_TYPE,
    check,
    find_mentions,
    load_evidence,
    term_pattern,
    whole_file_record_id,
)
from feeltriva_ingestion.features import load_case_features
from feeltriva_ingestion.load import RELEASE_ID, disease_candidate_id, source_id
from sqlalchemy import text

FILE = "matrix.csv"


def test_longest_term_wins_and_whole_words_only():
    terms = {"pain": "f_pain", "chest pain": "f_chest", "cold": "f_cold", "night sweats": "f_ns"}
    pattern = term_pattern(list(terms))
    sentence = "Chest  pain at rest, then pain again. Scolding is not cold."
    found = find_mentions(sentence, pattern, terms)
    assert found["f_chest"]["matched_text"] == "Chest  pain" and found["f_chest"]["mentions"] == 1
    assert found["f_pain"]["mentions"] == 1  # the second, separate "pain" only
    start = sentence.rindex("cold")  # the standalone word, not the letters inside "Scolding"
    assert found["f_cold"]["span"] == [start, start + 4] and found["f_cold"]["mentions"] == 1
    assert "f_ns" not in found


def test_negation_cue_is_recorded_per_sentence_not_guessed_away():
    terms = {"fever": "f_fever", "rash": "f_rash", "cough": "f_cough"}
    found = find_mentions(
        "There is no fever. A rash appears; patients never cough at night.", term_pattern(list(terms)), terms
    )
    assert found["f_fever"]["negation_cue_before_in_sentence"] is True
    assert found["f_rash"]["negation_cue_before_in_sentence"] is False  # the cue was in another sentence
    assert found["f_cough"]["negation_cue_before_in_sentence"] is True
    assert set(found) == {"f_fever", "f_rash", "f_cough"}  # a negated mention is still proposed


@pytest.fixture
def crafted(tmp_path, owner_db):
    tag = uuid.uuid4().hex[:10]
    flu, cold = f"Flu {tag}", f"Cold {tag}"
    rows = [
        f"{flu},1,1,1",  # row 1
        f"{flu},1,1,0",  # row 2: the two 'dup' columns disagree
        f"{flu},0,0,0",  # row 3: nothing affirmed
        f"{cold},1,0,0",  # row 4
        f"{flu},1,1,1",  # row 5: exact duplicate of row 1
    ]
    archive = f"evidence-{tag}.zip"
    path = tmp_path / archive
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(FILE, "disease,f1,dup,dup\n" + "\n".join(rows) + "\n")
    manifest = Manifest(
        {archive: sha256_file(path)},
        [
            {
                "archive": archive,
                "file": FILE,
                "expected_rows": 5,
                "exact_unique_rows": 4,
                "adapter": "positional_feature_matrix",
                "targets": ["source_records", "dataset_cases", "case_labels"],
            }
        ],
        [],
    )
    sid, narrative_sid = source_id(archive, FILE), f"src_narr_{tag}"
    f1, dup = f"feat_{tag}_f1", f"feat_{tag}_dup"
    terms = {
        "fever": f"zzfever{tag}",
        "severe": f"severe zzfever{tag}",
        "cough": f"zzcough{tag}",
        "rash": f"zzrash{tag}",
    }
    feature_ids = {key: f"feat_{tag}_{key}" for key in terms}
    with owner_db.transaction(None) as tx:
        if tx.get(MappingRelease, RELEASE_ID) is None:
            tx.add(MappingRelease(release_id=RELEASE_ID, version="lexical-0"))
        tx.add(Source(source_id=sid, source_name=f"{archive}/{FILE}", version="t", sha256="a" * 64))
        tx.add(Source(source_id=narrative_sid, source_name=f"narrative-{tag}", version="t", sha256="0" * 64))
        tx.add(Feature(feature_id=f1, preferred_name=f"f1 {tag}", kind="other", value_type="boolean"))
        tx.add(Feature(feature_id=dup, preferred_name=f"dup {tag}", kind="other", value_type="boolean"))
        for key, name in terms.items():
            tx.add(Feature(feature_id=feature_ids[key], preferred_name=name, kind="other", value_type="boolean"))
        narrative_disease = f"dis_{tag}"
        tx.add(Disease(disease_id=narrative_disease, preferred_name=f"narrative disease {tag}"))
        tx.flush()
        for index, feature in ((1, f1), (2, dup), (3, dup)):
            tx.add(
                FeatureMapping(
                    mapping_id=f"fm_{tag}_{index}",
                    release_id=RELEASE_ID,
                    source_id=sid,
                    file_path=FILE,
                    column_index=index,
                    original_term="f1" if index == 1 else "dup",
                    feature_id=feature,
                )
            )
        tx.add(
            SourceRecord(
                record_id=f"rec_{tag}_n",
                source_id=narrative_sid,
                file_path="symptoms.csv",
                row_number=1,
                content_hash="h",
                raw_object_uri="zip://synthetic",
            )
        )
        tx.flush()
        statements = {
            "symptom": (
                "symptom",
                narrative_disease,
                f"Patients have severe zzfever{tag} and zzcough{tag}. There is no zzrash{tag}.",
            ),
            "cause": ("cause", narrative_disease, f"A cause statement mentioning zzcough{tag}."),
            "orphan": ("symptom", None, f"No disease is attached, zzcough{tag}."),
        }
        for key, (kind, disease, content) in statements.items():
            tx.add(
                Statement(statement_id=f"st_{tag}_{key}", disease_id=disease, statement_type=kind, text_content=content)
            )
            tx.flush()
            tx.add(StatementSource(statement_id=f"st_{tag}_{key}", record_id=f"rec_{tag}_n"))
    url = os.environ.get("TEST_MIGRATION_DATABASE_URL", "")
    load_cases(tmp_path, url, manifest)
    load_case_features(tmp_path, url, manifest)
    return {
        "raw_dir": tmp_path,
        "archive": archive,
        "manifest": manifest,
        "tag": tag,
        "url": url,
        "sid": sid,
        "narrative_sid": narrative_sid,
        "f1": f1,
        "dup": dup,
        "flu": disease_candidate_id(flu),
        "cold": disease_candidate_id(cold),
        "features": feature_ids,
        "narrative_disease": narrative_disease,
    }


def _evidence(owner_db, where: str, params: dict):
    with owner_db.transaction(None) as tx:
        return [
            dict(r._mapping)
            for r in tx.execute(
                text(
                    f"""SELECT disease_id, feature_id, statement_id, record_id, relationship, context, frequency,
                       frequency_denominator, evidence_type, status
                FROM disease_feature_evidence WHERE {where} ORDER BY disease_id, feature_id"""
                ),
                params,
            )
        ]


@pytest.mark.postgres
def test_cooccurrence_is_a_per_source_sample_count_with_its_denominator(crafted, owner_db):
    c = crafted
    result = load_evidence(c["url"], c["manifest"], narrative_sources=[c["narrative_sid"]])
    rows = _evidence(owner_db, "record_id = :r", {"r": whole_file_record_id(c["sid"])})
    by = {(r["disease_id"], r["feature_id"]): r for r in rows}
    assert set(by) == {(c["flu"], c["f1"]), (c["flu"], c["dup"]), (c["cold"], c["f1"])}  # only pairs that occur

    flu_f1 = by[(c["flu"], c["f1"])]
    assert (float(flu_f1["frequency"]), flu_f1["frequency_denominator"]) == (0.75, 4)  # rows 1, 2, 5 of 4 flu rows
    flu_dup = by[(c["flu"], c["dup"])]
    # Two columns share the feature: rows 1 and 5 count once each, the disagreeing row 2 is not counted as present.
    assert (float(flu_dup["frequency"]), flu_dup["frequency_denominator"]) == (0.5, 4)
    assert flu_dup["context"]["cases_with_feature"] == 2 and flu_dup["context"]["cases_with_conflicting_values"] == 1
    assert (float(by[(c["cold"], c["f1"])]["frequency"]), by[(c["cold"], c["f1"])]["frequency_denominator"]) == (1.0, 1)

    for row in rows:
        assert (row["evidence_type"], row["relationship"], row["status"]) == (
            COOCCURRENCE_TYPE,
            "co_occurs_in_source_sample",
            "pending",
        )
        assert row["statement_id"] is None and row["record_id"] == whole_file_record_id(c["sid"])
        context = row["context"]
        assert context["sample_count_not_prevalence"] is True and context["sources_pooled"] is False
        assert context["source"] == f"{c['archive']}/{FILE}" and context["feature_meaning"] == "unclassified"
    # Duplicates behind the denominator are stated, not hidden: rows 1 and 5 are one profile.
    assert flu_f1["context"]["exact_duplicate_rows_with_label"] == 2
    assert flu_f1["context"]["distinct_profiles_with_label"] == 3

    source = result["cooccurrence"]["per_source"][f"{c['archive']}/{FILE}"]
    assert source["pairs"] == 3 and source["labels"] == 2 and source["columns_sharing_a_feature"] == 2
    assert check(result) == []

    with owner_db.transaction(None) as tx:
        record = tx.get(SourceRecord, whole_file_record_id(c["sid"]))
        assert (record.row_number, record.quality_flags, record.content_hash) == (None, ["whole_file_record"], "a" * 64)


@pytest.mark.postgres
def test_narrative_mentions_are_proposals_tied_to_their_statement(crafted, owner_db):
    c = crafted
    result = load_evidence(c["url"], c["manifest"], narrative_sources=[c["narrative_sid"]])
    rows = _evidence(owner_db, "statement_id LIKE :s", {"s": f"st_{c['tag']}_%"})
    by = {r["feature_id"]: r for r in rows}
    features = c["features"]
    assert set(by) == {features["severe"], features["cough"], features["rash"]}
    assert features["fever"] not in by  # swallowed by the longer term "severe zzfever…"
    for row in rows:
        assert row["statement_id"] == f"st_{c['tag']}_symptom"  # not the cause statement, not the orphan
        assert (row["evidence_type"], row["relationship"], row["status"]) == (
            NARRATIVE_TYPE,
            "mentioned_in_symptom_statement",
            "pending",
        )
        assert row["record_id"] is None and row["frequency"] is None and row["frequency_denominator"] is None
        assert row["disease_id"] == c["narrative_disease"] and row["context"]["a_mention_is_not_an_assertion"] is True
    assert by[features["rash"]]["context"]["negation_cue_before_in_sentence"] is True
    assert by[features["cough"]]["context"]["negation_cue_before_in_sentence"] is False
    statement = f"Patients have severe zzfever{c['tag']} and zzcough{c['tag']}. There is no zzrash{c['tag']}."
    start, end = by[features["cough"]]["context"]["span"]
    assert statement[start:end] == f"zzcough{c['tag']}"  # the span points at the words
    assert result["narrative"]["statements"] == 1 and result["narrative"]["proposals"] == 3
    assert result["narrative"]["with_negation_cue"] == 1


@pytest.mark.postgres
def test_rerun_inserts_nothing_and_other_loaders_still_accept_the_file(crafted, owner_db):
    c = crafted
    load_evidence(c["url"], c["manifest"], narrative_sources=[c["narrative_sid"]])
    before = _evidence(
        owner_db,
        "record_id = :r OR statement_id LIKE :s",
        {"r": whole_file_record_id(c["sid"]), "s": f"st_{c['tag']}_%"},
    )
    again = load_evidence(c["url"], c["manifest"], narrative_sources=[c["narrative_sid"]])
    assert again["narrative"]["proposals_inserted"] == 0 and again["cooccurrence"]["proposals_inserted"] == 0
    assert (
        _evidence(
            owner_db,
            "record_id = :r OR statement_id LIKE :s",
            {"r": whole_file_record_id(c["sid"]), "s": f"st_{c['tag']}_%"},
        )
        == before
    )
    # The whole-file record now exists for this source. Row counts must still be 5, not 6.
    cases = load_cases(c["raw_dir"], c["url"], c["manifest"])
    assert cases["summary"][f"{c['archive']}/{FILE}"]["records"] == 5
    features = load_case_features(c["raw_dir"], c["url"], c["manifest"])
    assert features["files"][f"{c['archive']}/{FILE}"]["rows_inserted"] == 0


@pytest.mark.postgres
def test_every_stored_proposal_is_pending_and_has_provenance(crafted, owner_db):
    c = crafted
    result = load_evidence(c["url"], c["manifest"], narrative_sources=[c["narrative_sid"]])
    assert set(result["stored"]) >= {COOCCURRENCE_TYPE, NARRATIVE_TYPE}
    for stored in result["stored"].values():
        assert stored["changed_by_no_reviewer"] == 0 and stored["without_provenance"] == 0
        assert stored["frequency_without_denominator"] == 0 and stored["frequency_out_of_range"] == 0
    assert re.fullmatch(r"recf_[0-9a-f]{16}", whole_file_record_id(c["sid"]))


@pytest.mark.postgres
def test_a_proposal_a_reviewer_decided_passes_the_check_and_one_changed_by_nobody_does_not(crafted, owner_db):
    """M2.5d1. The check used to report every evidence row that was not pending (BUG-021)."""
    c = crafted

    def run():
        return load_evidence(c["url"], c["manifest"], narrative_sources=[c["narrative_sid"]])

    run()
    with owner_db.transaction(None) as tx:
        decided, changed = tx.execute(
            text("SELECT evidence_id FROM disease_feature_evidence WHERE record_id = :r ORDER BY evidence_id LIMIT 2"),
            {"r": whole_file_record_id(c["sid"])},
        ).scalars()
    approve = text("UPDATE disease_feature_evidence SET status = 'approved' WHERE evidence_id = :e")
    note = text(
        "INSERT INTO review_notes (note_id, target_type, target_id, reviewer, note, status_change) "
        "VALUES (:n, 'evidence', :e, 'dev-reviewer:test', 'Decided in a test.', :s)"
    )
    try:
        # Approved, with the decision recorded as the review path records it: in order.
        with owner_db.transaction(None) as tx:
            tx.execute(approve, {"e": decided})
            tx.execute(note, {"n": uuid.uuid4(), "e": decided, "s": "approved"})
        result = run()
        assert check(result) == [] and result["stored"][COOCCURRENCE_TYPE]["changed_by_no_reviewer"] == 0
        # Approved with no decision behind it: reported.
        with owner_db.transaction(None) as tx:
            tx.execute(approve, {"e": changed})
        assert check(run()) == [f"{COOCCURRENCE_TYPE}: 1 rows changed by no reviewer"]
        # A decision recorded for another status than the row has does not cover it.
        with owner_db.transaction(None) as tx:
            tx.execute(note, {"n": uuid.uuid4(), "e": changed, "s": "rejected"})
        assert check(run()) == [f"{COOCCURRENCE_TYPE}: 1 rows changed by no reviewer"]
    finally:  # the check reads the whole table, and other tests share this database
        with owner_db.transaction(None) as tx:
            ids = {"a": decided, "b": changed}
            tx.execute(
                text("UPDATE disease_feature_evidence SET status = 'pending' WHERE evidence_id IN (:a, :b)"), ids
            )
            tx.execute(text("DELETE FROM review_notes WHERE target_type = 'evidence' AND target_id IN (:a, :b)"), ids)
    assert check(run()) == []
