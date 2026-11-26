"""Duplicates in the stored data (M2.18): which condition names are one condition by rule, which name is kept,
what is left for a person, and that merging deletes nothing."""

from __future__ import annotations

import uuid

import pytest
from feeltriva_api import duplicates
from feeltriva_api.auth import Principal
from feeltriva_api.models import (
    Disease,
    DiseaseMapping,
    MappingRelease,
    RelationSuggestion,
    ReviewNote,
    Source,
    Statement,
    TerminologyLink,
)
from sqlalchemy import select

WHO = Principal(subject="dev-reviewer:dedupe", roles=frozenset({"reviewer"}))


@pytest.fixture
def labels(owner_db):
    """Invented condition names with the suggestions the look-ups would have made for them."""
    tag = uuid.uuid4().hex[:8]
    names = {
        "cold": f"pretend cold {tag}",
        "cold_": f"pretend_cold_{tag}",
        "attack": f"pretend attack {tag}",
        "infarct": f"pretend infarction {tag}",
        "short": f"pa{tag}",
        "croup": f"pretend croup {tag}",
        "larynx": f"pretend laryngitis {tag}",
        "two_a": f"pretend twofold {tag}",
        "two_b": f"pretend double {tag}",
        "alone": f"pretend alone {tag}",
    }
    with owner_db.transaction(None, role="migration") as tx:
        tx.add(MappingRelease(release_id=f"dd-{tag}", version=f"dd-{tag}-1"))
        tx.add(Source(source_id=f"src_{tag}_1", source_name=f"one-{tag}.csv", version="1", sha256=f"a{tag}"))
        tx.add(Source(source_id=f"src_{tag}_2", source_name=f"two-{tag}.csv", version="1", sha256=f"b{tag}"))
        for key, name in names.items():
            tx.add(Disease(disease_id=f"dis_{tag}_{key}", preferred_name=name))
        tx.flush()
        # "pretend attack" is named by two files, the others by one or none.
        for n, (key, source) in enumerate((("attack", 1), ("attack", 2), ("infarct", 1), ("cold_", 1))):
            tx.add(
                DiseaseMapping(
                    mapping_id=f"dm_{tag}_{n}",
                    release_id=f"dd-{tag}",
                    source_id=f"src_{tag}_{source}",
                    original_label=names[key],
                    disease_id=f"dis_{tag}_{key}",
                    method="lexical_casefold_whitespace",
                )
            )
        # The reference entry both "attack" names and the abbreviation are matched to; its title is one of our names.
        tx.add(
            TerminologyLink(
                link_id=f"tl_{tag}_infarct",
                disease_id=f"dis_{tag}_infarct",
                system="MONDO",
                system_version="t",
                code=f"MONDO:{tag}",
                title=f"Pretend Infarction {tag}",
                uri="u",
                match_method="exact_label",
                detail={},
            )
        )

        def suggest(key, left, right, relation, signals):
            tx.add(
                RelationSuggestion(
                    suggestion_id=f"rs_{tag}_{key}",
                    subject_type="disease",
                    relation=relation,
                    left_id=f"dis_{tag}_{left}",
                    right_id=f"dis_{tag}_{right}",
                    left_label=names[left],
                    right_label=names[right],
                    signals=signals,
                )
            )

        same = [{"signal": "same_standard_code", "vocabulary": "MONDO", "code": f"MONDO:{tag}", "release": "t"}]
        suggest("cold", "cold", "cold_", "possible_synonym", [{"signal": "same_words_other_punctuation"}])
        suggest("attack", "attack", "infarct", "possible_synonym", same)
        suggest(
            "short",
            "short",
            "infarct",
            "possible_synonym",
            [*same, {**same[0], "vocabulary": "ICD-11 MMS", "code": "X1"}],
        )
        suggest("croup", "larynx", "croup", "possible_synonym", same)
        # One list matches these two names to two of its entries: not for a rule.
        suggest(
            "two1",
            "two_a",
            "two_b",
            "possible_synonym",
            [{**same[0], "code": "MONDO:a"}, {**same[0], "code": "MONDO:b"}],
        )
        suggest("kind", "alone", "cold", "possible_subtype", [{"signal": "adds_words", "words": ["alone"]}])
        for key in ("a", "b"):
            tx.add(
                Statement(
                    statement_id=f"st_{tag}_{key}",
                    disease_id=f"dis_{tag}_{'attack' if key == 'a' else 'infarct'}",
                    statement_type="symptom",
                    text_content=f"The same sentence about it ({tag}).",
                )
            )
    return tag, names


def _mine(found, tag):
    groups = [group for group in found["groups"] if tag in " ".join(group["names"])]
    left = [entry for entry in found["left_for_a_person"] if tag in " ".join(entry["names"])]
    return groups, left


def test_names_are_compared_as_plain_words_and_an_unclear_exception_is_refused(tmp_path):
    assert duplicates.plain("Guillain-Barre_syndrome  (GBS)") == "guillain barre syndrome gbs"
    path = tmp_path / "exceptions.json"
    path.write_text('{"not_merged": [{"names": ["a", "b"], "reason": "r", "noted_on": "2026-11-25"}]}')
    assert duplicates.load_exceptions(path)[0]["names"] == ["a", "b"]
    path.write_text('{"not_merged": [{"names": ["a"], "reason": "r", "noted_on": "2026-11-25"}]}')
    with pytest.raises(ValueError, match="two names, a reason and a date"):
        duplicates.load_exceptions(path)
    assert duplicates.load_exceptions(tmp_path / "none.json") == []
    # The file of the repository is well formed, and every pair in it gives a reason.
    assert all(len(entry["names"]) == 2 and entry["reason"] for entry in duplicates.load_exceptions())


def test_groups_keep_one_of_our_own_names_and_leave_the_doubtful_ones_for_a_person(labels, owner_db):
    tag, names = labels
    exceptions = [{"names": [names["larynx"], names["croup"]], "reason": "not sure they are one", "noted_on": "x"}]
    with owner_db.transaction(None, role="migration") as tx:
        groups, left = _mine(duplicates.condition_groups(tx, exceptions), tag)
    by = {group["kept_name"]: group for group in groups}
    # Same words, other punctuation: the spelling without the underscore is kept, whichever file count it has.
    cold = by[names["cold"]]
    assert (cold["kept_id"], cold["merged"], cold["standard_entry"]) == (f"dis_{tag}_cold", [f"dis_{tag}_cold_"], None)
    # Three names, one entry in each of two lists: one group. The name that is the entry's title is kept, in our
    # lower case; the abbreviation and the everyday name become other names of it.
    attack = by[names["infarct"]]
    assert attack["kept_id"] == f"dis_{tag}_infarct" and attack["standard_entry"]["vocabulary"] == "MONDO"
    assert sorted(attack["merged"]) == sorted([f"dis_{tag}_attack", f"dis_{tag}_short"])
    assert len(groups) == 2
    # Left for a person: the pair on the list of exceptions, and the pair one list matches to two of its entries.
    assert sorted(entry["reason"] for entry in left) == [
        "not sure they are one",
        "one reference list matches these names to more than one of its entries",
    ]
    # A suggestion that one name is a kind of another is never a reason to merge.
    assert not any(f"dis_{tag}_alone" in [group["kept_id"], *group["merged"]] for group in groups)


def test_merging_deletes_nothing_records_who_and_why_and_a_second_run_finds_nothing(labels, owner_db, container):
    tag, names = labels
    exceptions = [{"names": [names["larynx"], names["croup"]], "reason": "not sure they are one", "noted_on": "x"}]
    with owner_db.transaction(None, role="migration") as tx:
        groups, _left = _mine(duplicates.condition_groups(tx, exceptions), tag)
        assert [entry["copies"] for entry in duplicates.duplicate_texts(tx) if tag in entry["kept"]] == []
    done = duplicates.merge_groups(container.db, WHO, groups, "Two names for one condition (test).")
    assert (done["groups"], done["names_merged"], done["merges_refused"], done["suggestions_approved"]) == (2, 3, [], 3)
    with owner_db.transaction(None, role="migration") as tx:
        rows = {
            row.disease_id.rsplit(f"{tag}_", 1)[1]: row
            for row in tx.scalars(select(Disease).where(Disease.disease_id.like(f"dis_{tag}_%")))
        }
        # Every name is still there: a merged one points to the name kept and is no longer used by itself.
        assert len(rows) == len(names)
        assert {key: (rows[key].redirected_to, rows[key].status) for key in ("attack", "short", "cold_")} == {
            "attack": (f"dis_{tag}_infarct", "retired"),
            "short": (f"dis_{tag}_infarct", "retired"),
            "cold_": (f"dis_{tag}_cold", "retired"),
        }
        assert rows["infarct"].preferred_name == names["infarct"] and rows["larynx"].redirected_to is None
        decided = tx.scalars(
            select(RelationSuggestion).where(RelationSuggestion.suggestion_id.like(f"rs_{tag}_%"))
        ).all()
        assert {row.suggestion_id.rsplit("_", 1)[1]: (row.status, row.reviewer) for row in decided} == {
            "cold": ("approved", WHO.subject),
            "attack": ("approved", WHO.subject),
            "short": ("approved", WHO.subject),
            "croup": ("pending", None),
            "two1": ("pending", None),
            "kind": ("pending", None),
        }
        # Once the two names are one condition, the sentence stored for each of them is the same text twice.
        twice = [entry for entry in duplicates.duplicate_texts(tx) if tag in entry["kept"]]
        assert twice == [{"condition": f"dis_{tag}_infarct", "kept": f"st_{tag}_a", "copies": [f"st_{tag}_b"]}]
        again, _ = _mine(duplicates.condition_groups(tx, exceptions), tag)
        assert again == []  # nothing is merged twice
    # Only this test's own condition: the test database also holds the real archives, whose rows other tests count.
    mine = frozenset({f"dis_{tag}_infarct"})
    retired = duplicates.retire_duplicate_texts(container.db, WHO, "Tidied (test).", conditions=mine)
    assert (retired["sets"], retired["copies_retired"], retired["refused"]) == (1, 1, [])
    with owner_db.transaction(None, role="migration") as tx:
        assert {key: tx.get(Statement, f"st_{tag}_{key}").status for key in "ab"} == {"a": "pending", "b": "retired"}
        note = tx.scalars(select(ReviewNote).where(ReviewNote.target_id == f"st_{tag}_b")).one()
        assert note.note == f"Tidied (test). A word-for-word copy of the text st_{tag}_a of the same condition."
        assert note.reviewer == WHO.subject and duplicates.report(owner_db)["texts_stored_twice_for_one_condition"] >= 0


def test_the_list_of_condition_names_gives_the_data_file_so_that_one_name_in_two_files_reads_as_two_rows(
    labels, client
):
    tag, names = labels
    listed = client.get(
        "/internal/v1/review/disease-mappings",
        params={"q": names["attack"]},
        headers={"Authorization": "Bearer dev-reviewer:dedupe"},
    ).json()
    assert listed["total"] == 2  # the same name, once for each of the two files that use it
    assert sorted(item["source_name"] for item in listed["items"]) == [f"one-{tag}.csv", f"two-{tag}.csv"]
    assert {item["original_term"] for item in listed["items"]} == {names["attack"]}
