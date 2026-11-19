"""Candidate links to ICD-11 and LOINC (M2.11). No test here touches the network: the ICD API is
replaced by a function that answers from a table, and LOINC by a small crafted release."""

from __future__ import annotations

import base64
import csv
import json
import os
import urllib.error
import urllib.parse
import uuid
import zipfile

import pytest
from feeltriva_api.models import Disease, DiseaseMapping, Feature, FeatureMapping, MappingRelease, Source
from feeltriva_ingestion.archives import ArchiveError, sha256_file
from feeltriva_ingestion.load import RELEASE_ID, source_id
from feeltriva_ingestion.vocabulary import (
    ICD,
    LOINC,
    IcdClient,
    IcdSettings,
    best_result,
    check,
    exact_matches,
    link_vocabularies,
    loinc_matches,
    loinc_table,
    plain,
    query_for,
    summarise,
    write_review,
)
from sqlalchemy import text

SETTINGS = IcdSettings(_env_file=None, icd_api_client_id="id-1", icd_api_client_secret="s3cret")  # noqa: S106 - a test value


def entity(code, title, chapter="21", score=1.0, names=(), **more):
    pvs = [{"propertyId": kind, "label": label, "score": 1} for kind, label in names]
    return {
        "theCode": code,
        "title": title,
        "id": f"http://id.who.int/icd/release/11/2026-01/mms/{code}",
        "chapter": chapter,
        "score": score,
        "matchingPVs": pvs,
        **more,
    }


class FakeApi:
    """Answers like the WHO ICD API v2, from a table of search replies."""

    def __init__(self, replies):
        self.replies, self.seen, self.tokens, self.fail_once = replies, [], 0, False

    def __call__(self, url, headers, body):
        if "connect/token" in url:
            self.tokens += 1
            assert headers["Authorization"] == "Basic " + base64.b64encode(b"id-1:s3cret").decode()
            assert urllib.parse.parse_qs(body.decode()) == {
                "grant_type": ["client_credentials"],
                "scope": ["icdapi_access"],
            }
            return {"access_token": f"token-{self.tokens}", "token_type": "Bearer", "expires_in": 3600}
        assert (
            headers["API-Version"] == "v2"
            and headers["Accept-Language"] == "en"
            and headers["Authorization"].startswith("Bearer token-")
        )
        if self.fail_once:
            self.fail_once = False
            raise urllib.error.HTTPError(url, 401, "expired", None, None)  # type: ignore[arg-type]
        if url.endswith("/icd/release/11/mms"):
            return {"latestRelease": "http://id.who.int/icd/release/11/2026-01/mms"}
        if url.endswith("/2026-01/mms"):
            return {"child": ["http://id.who.int/icd/release/11/2026-01/mms/ch21"]}
        if url.endswith("/mms/ch21"):
            return {"code": "21", "title": {"@value": "Symptoms, signs or clinical findings, not elsewhere classified"}}
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        assert query["flatResults"] == ["true"] and query["medicalCodingMode"] == ["true"]
        self.seen.append(query["q"][0])
        return {"destinationEntities": self.replies.get(query["q"][0], [])}


def test_names_are_compared_as_plain_words_and_naming_words_are_dropped():
    assert plain("Gastro-oesophageal  Reflux_Disease") == "gastro oesophageal reflux disease"
    assert query_for("joint_pain symptom") == "joint pain" and query_for("angiokeratomas rare") == "angiokeratomas"
    assert query_for("symptom of the eye") == "symptom of the eye"  # only the trailing naming word is dropped


def test_only_an_entity_carrying_exactly_the_name_is_a_match():
    reply = {
        "destinationEntities": [
            entity("MD12", "Cough", names=[("Synonym", "coughing")]),
            entity(
                "1C12.Z",
                "Whooping cough, unspecified",
                "01",
                0.53,
                [("TitleOfOtherEntity", "Whooping cough")],
                isResidualUnspecified=True,
            ),
            {"title": "Cough", "chapter": "21", "score": 1},  # a grouping without a code is not a link target
        ]
    }
    assert [(m["code"], m["method"], m["chapter"]) for m in exact_matches("cough", reply)] == [
        ("MD12", "exact_title", "21")
    ]
    whooping = exact_matches("Whooping-Cough", reply)
    assert [(m["code"], m["method"], m["residual"]) for m in whooping] == [("1C12.Z", "exact_titleofotherentity", True)]
    assert exact_matches("coughing", reply)[0]["method"] == "exact_synonym"
    assert exact_matches("chronic cough", reply) == []  # close is not the same name: no link
    assert (
        best_result(reply) == {"code": "MD12", "title": "Cough", "score": 1.0, "chapter": "21"}
        and best_result({}) is None
    )


def test_the_client_asks_for_one_token_caches_answers_and_renews_an_expired_token(tmp_path):
    api = FakeApi({"cough": [entity("MD12", "Cough")]})
    client = IcdClient(SETTINGS, tmp_path / "cache", api, pause=0)
    assert client.release() == "2026-01" and client.chapters("2026-01")["21"].startswith("Symptoms, signs")
    first = client.search("2026-01", "cough")
    calls = client.calls
    assert (
        client.search("2026-01", "cough") == first and client.calls == calls and api.seen == ["cough"]
    )  # answered from disk
    assert api.tokens == 1
    api.fail_once = True
    client.search("2026-01", "fever")
    assert api.tokens == 2  # a 401 makes it fetch a new token and try again
    again = IcdClient(SETTINGS, tmp_path / "cache", api, pause=0)
    again.search("2026-01", "cough")
    assert again.calls == 0  # a new run reuses the cache and asks the API nothing
    with pytest.raises(SystemExit, match="ICD_API_CLIENT_ID"):
        IcdClient(IcdSettings(_env_file=None), tmp_path / "empty", api, pause=0).release()


def test_a_dropped_connection_is_retried_and_a_dead_one_ends_with_a_plain_message(tmp_path):
    api = FakeApi({"cough": [entity("MD12", "Cough")]})
    failures = {"left": 2}

    def flaky(url, headers, body):
        if "search" in url and failures["left"]:
            failures["left"] -= 1
            raise urllib.error.URLError("The handshake operation timed out")
        return api(url, headers, body)

    client = IcdClient(SETTINGS, tmp_path / "cache", flaky, pause=0, retry_wait=0)
    assert client.search("2026-01", "cough")["destinationEntities"][0]["theCode"] == "MD12" and failures["left"] == 0

    def dead(url, headers, body):
        if "connect/token" in url:
            return api(url, headers, body)
        raise TimeoutError("timed out")

    with pytest.raises(SystemExit, match="could not be reached after 5 attempts.*run the command again"):
        IcdClient(SETTINGS, tmp_path / "other", dead, pause=0, retry_wait=0).search("2026-01", "fever")
    assert not list((tmp_path / "other").glob("*.json"))  # a failed call leaves nothing behind in the cache


LOINC_ROWS = (
    "LOINC_NUM,COMPONENT,SCALE_TYP,SHORTNAME,LONG_COMMON_NAME,STATUS,CLASSTYPE,EXAMPLE_UCUM_UNITS\n"
    "39156-5,Body mass index,Qn,BMI,Body mass index (BMI) [Ratio],ACTIVE,2,kg/m2\n"
    "8867-4,Heart rate,Qn,Heart rate,Heart rate,ACTIVE,2,{beats}/min\n"
    "0000-1,Body mass index,Qn,BMI,Old body mass index,DEPRECATED,2,kg/m2\n"
    "0000-2,Glucose,Qn,Glucose,Glucose [Mass/volume] in Blood,ACTIVE,1,mg/dL\n"
    "85730-0,Fever,Ord,Fever Mother,Fever in Mother,ACTIVE,2,\n"
    "81660-3,Nausea,Ord,Nausea,Nausea [Presence],ACTIVE,2,\n"
)


def _loinc(tmp_path):
    path = tmp_path / "loinc.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("LoincTable/Loinc.csv", LOINC_ROWS)
    return {"name": "loinc.zip", "sha256": sha256_file(path), "version": "9.99", "table": "LoincTable/Loinc.csv"}


def test_loinc_terms_are_found_by_exact_name_or_for_a_measurement_question(tmp_path):
    entry = _loinc(tmp_path)
    table = loinc_table(tmp_path, entry)
    assert [row["LOINC_NUM"] for row in table] == [
        "39156-5",
        "8867-4",
        "85730-0",
        "81660-3",
    ]  # active clinical terms only
    assert loinc_matches("fever", "symptom", table) == []  # "Fever" is only the component of "Fever in Mother"
    assert [m["code"] for m in loinc_matches("nausea", "symptom", table)] == ["81660-3"]  # "Nausea [Presence]"
    assert [(m["code"], m["method"], m["units"]) for m in loinc_matches("heart rate", "symptom", table)] == [
        ("8867-4", "exact_name", "{beats}/min")
    ]
    question = "Is your BMI less than 18.5, or are you underweight?"
    assert [(m["code"], m["method"]) for m in loinc_matches(question, "measurement", table)] == [
        ("39156-5", "short_name_in_question")
    ]
    assert loinc_matches(question, "history", table) == []  # only a measurement question is matched by a short name
    assert loinc_matches("increased heart rate", "symptom", table) == []
    with pytest.raises(ArchiveError, match="does not match"):
        loinc_table(tmp_path, {**entry, "sha256": "0" * 64})


@pytest.mark.postgres
def test_exact_name_matches_become_pending_links_and_nothing_else_does(tmp_path, owner_db):
    tag = uuid.uuid4().hex[:10]
    sid = source_id(f"vocab-{tag}.zip", "data.csv")
    flu, unknown, cough, bmi = (
        f"synthetic flu {tag}",
        f"unknown thing {tag}",
        f"cough {tag}",
        f"E_1_is_your_bmi_less_than_{tag}",
    )
    with owner_db.transaction(None) as tx:
        if tx.get(MappingRelease, RELEASE_ID) is None:
            tx.add(MappingRelease(release_id=RELEASE_ID, version="lexical-0"))
        tx.add(Source(source_id=sid, source_name=f"vocab-{tag}.zip/data.csv", version="t", sha256="0"))
        for n, name in enumerate((flu, unknown)):
            tx.add(Disease(disease_id=f"dis_{tag}_{n}", preferred_name=name))
        tx.add(
            Feature(feature_id=f"feat_{tag}_c", preferred_name=f"{cough} symptom", kind="symptom", value_type="boolean")
        )
        tx.add(Feature(feature_id=f"feat_{tag}_b", preferred_name=bmi, kind="measurement", value_type="boolean"))
        tx.flush()
        for n, name in enumerate((flu, unknown)):
            tx.add(
                DiseaseMapping(
                    mapping_id=f"dm_{tag}_{n}",
                    release_id=RELEASE_ID,
                    source_id=sid,
                    original_label=name,
                    disease_id=f"dis_{tag}_{n}",
                    method="lexical_casefold_whitespace",
                )
            )
        tx.add(
            FeatureMapping(
                mapping_id=f"fm_{tag}_c",
                release_id=RELEASE_ID,
                source_id=sid,
                file_path="data.csv",
                column_index=1,
                original_term=f"symptom_{cough}",
                feature_id=f"feat_{tag}_c",
            )
        )
        tx.add(
            FeatureMapping(
                mapping_id=f"fm_{tag}_b",
                release_id=RELEASE_ID,
                source_id=sid,
                file_path="data.csv",
                column_index=2,
                original_term=bmi,
                feature_id=f"feat_{tag}_b",
                transformation={
                    "source_dictionary": {"question": "Is your BMI less than 18.5, or are you underweight?"}
                },
            )
        )
    api = FakeApi(
        {
            flu: [entity("XA01", f"Synthetic flu {tag}", "01"), entity("XA02", "Another flu", "01", 0.6)],
            unknown: [entity("XB07", "Something nearby", "05", 0.71)],
            cough: [entity("MD12", "Cough", "21", names=[("Synonym", cough)])],
        }
    )
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]

    def run():
        return link_vocabularies(
            tmp_path, url, IcdClient(SETTINGS, tmp_path / "cache", api, pause=0), _loinc(tmp_path), [sid]
        )

    result = run()
    assert check(result) == [] and result["release"] == "2026-01"
    assert sorted(api.seen) == sorted(
        [flu, unknown, cough]
    )  # the question sentence was never sent; "symptom" was dropped
    by = {item["name"]: item for item in result["items"]}
    assert [(link["system"], link["code"], link["method"]) for link in by[flu]["links"]] == [
        (ICD, "XA01", "exact_title")
    ]
    assert by[unknown]["links"] == [] and by[unknown]["best"] == {
        "code": "XB07",
        "title": "Something nearby",
        "score": 0.71,
        "chapter": "05",
    }
    assert [
        (link["code"], link["method"], link["detail"]["chapter_title"][:8]) for link in by[f"{cough} symptom"]["links"]
    ] == [("MD12", "exact_synonym", "Symptoms")]
    assert [(link["system"], link["code"]) for link in by[bmi]["links"]] == [(LOINC, "39156-5")] and by[bmi][
        "sent"
    ] == ""
    assert result["inserted"] == {ICD: 2, LOINC: 1}
    counts = summarise(result)["rows"]
    assert (
        counts[("disease", "name found in ICD-11")] == 1
        and counts[("disease", "no entity with exactly this name")] == 1
    )
    assert counts[("feature (measurement)", "not sent: a question sentence, not a name")] == 1

    with owner_db.transaction(None) as tx:
        rows = tx.execute(
            text(
                """SELECT system, system_version, code, title, uri, match_method, status::text, disease_id, feature_id
                   FROM terminology_links WHERE disease_id LIKE :p OR feature_id LIKE :q ORDER BY code"""
            ),
            {"p": f"dis_{tag}_%", "q": f"feat_{tag}_%"},
        ).all()
        # Since M2.17 the API role may read these rows and set a decision, inside a reviewer transaction only
        # (tests/api/test_review_links.py). It still cannot write a code or a title, nor add or remove a link.
        guarded = tx.execute(
            text(
                """SELECT (SELECT relrowsecurity FROM pg_class WHERE relname = 'terminology_links'),
                          has_column_privilege('feeltriva_app', 'terminology_links', 'code', 'UPDATE'),
                          has_column_privilege('feeltriva_app', 'terminology_links', 'title', 'UPDATE'),
                          has_table_privilege('feeltriva_app', 'terminology_links', 'INSERT'),
                          has_table_privilege('feeltriva_app', 'terminology_links', 'DELETE')"""
            )
        ).one()
    assert [(r[0], r[1], r[2], r[5], r[6]) for r in rows] == [
        (LOINC, "9.99", "39156-5", "short_name_in_question", "pending"),
        (ICD, "2026-01", "MD12", "exact_synonym", "pending"),
        (ICD, "2026-01", "XA01", "exact_title", "pending"),
    ]
    assert all(r[3] and r[4] for r in rows)  # code, title and URI are always stored together
    assert [bool(r[7]) != bool(r[8]) for r in rows] == [True, True, True]
    assert tuple(guarded) == (True, False, False, False, False)
    assert sum(run()["inserted"].values()) == 0  # a rerun adds nothing, and asks the API nothing new
    with write_review(result, tmp_path / "review").open(encoding="utf-8", newline="") as handle:
        review = {row["name"]: row for row in csv.DictReader(handle)}
    assert (review[unknown]["code"], review[unknown]["best_code"], review[unknown]["best_score"]) == (
        "",
        "XB07",
        "0.71",
    )
    assert (review[flu]["code"], review[flu]["uri"][:22], review[flu]["match"]) == (
        "XA01",
        "http://id.who.int/icd/",
        "exact_title",
    )
    assert json.loads(
        (tmp_path / "cache").glob("*.json").__next__().read_text()
    )  # answers are kept on disk, outside Git

    # BUG-021: a link decided by a named reviewer is not a difference; a decision nobody signed is.
    decided = {"d": f"dis_{tag}_0"}
    with owner_db.transaction(None) as tx:
        tx.execute(
            text(
                "UPDATE terminology_links SET status = 'rejected', reviewer = 'dev-reviewer:test' WHERE disease_id = :d"
            ),
            decided,
        )
    assert check(run()) == []
    try:
        with owner_db.transaction(None) as tx:
            tx.execute(text("UPDATE terminology_links SET reviewer = NULL WHERE disease_id = :d"), decided)
        assert check(run()) == ["1 links were decided without a recorded reviewer; only a reviewer may decide a link"]
    finally:  # the check reads the whole table: leave no unsigned decision behind for other tests
        with owner_db.transaction(None) as tx:
            tx.execute(
                text("UPDATE terminology_links SET reviewer = 'dev-reviewer:test' WHERE disease_id = :d"), decided
            )
