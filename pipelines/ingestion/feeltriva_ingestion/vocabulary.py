"""Candidate links to standard vocabularies: ICD-11 and LOINC (M2.11, owner decision E51).

For each disease candidate and each named symptom, history or exposure term, the WHO ICD-11
search is asked for the term, and a link is stored only when an ICD-11 entity carries exactly
that name (as its title or as one of its listed names). Everything else gets no link: the best
search result is written to the review file for a person to judge. Measurement items are looked
up in the LOINC release the owner supplied.

What leaves this machine: the term itself (a column heading or a disease label), sent to the
WHO ICD API. Never a case row, never a count. Results are cached under `data/derived/`, outside
Git, so a rerun asks the API nothing it has already been asked.

Licence conditions observed (WHO terms of use, LOINC licence 5.8):

- each stored ICD link keeps code, title and URI together;
- no mapping between ICD-11 and another classification or terminology is produced: every item
  is coded in each vocabulary on its own, and the links are not published;
- the required credits are in `README.md`.

Links are candidates with review status `pending`. A match of names is not a clinical judgement.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import http.client
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from feeltriva_api.settings import Settings
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine

from .archives import RAW_DIR, ROOT, ArchiveError, sha256_file
from .cases import _raw_cursor
from .meanings import is_question

TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"  # noqa: S105 - an address, not a secret
API = "https://id.who.int"
ICD, LOINC = "ICD-11 MMS", "LOINC"
CACHE_DIR = ROOT / "data" / "derived" / "icd_cache"
REVIEW_DIR = ROOT / "data" / "derived" / "review"
# Words the source's column naming adds to a term (`symptom_*`, `*_rare`); they are not part of the name.
_NAMING_WORDS = re.compile(r"\s+(symptom|rare)$")
_BRACKET = re.compile(r"\s*\[[^\]]*\]\s*$")
Fetch = Callable[[str, dict[str, str], bytes | None], dict[str, Any]]


class IcdSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    icd_api_client_id: str = ""
    icd_api_client_secret: str = ""


_connections: dict[str, http.client.HTTPSConnection] = {}


def _fetch(url: str, headers: dict[str, str], body: bytes | None) -> dict[str, Any]:
    """One HTTPS request over a connection that is kept open between calls to the same host."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https":
        raise ValueError(f"only https is used: {url}")
    connection = _connections.get(parts.netloc)
    if connection is None:
        connection = _connections[parts.netloc] = http.client.HTTPSConnection(parts.netloc, timeout=20)
    try:
        connection.request(
            "POST" if body is not None else "GET",
            parts.path + (f"?{parts.query}" if parts.query else ""),
            body,
            headers,
        )
        response = connection.getresponse()
        data = response.read()
    except (http.client.HTTPException, OSError):
        connection.close()
        _connections.pop(parts.netloc, None)
        raise
    if response.status >= 400:
        raise urllib.error.HTTPError(url, response.status, response.reason, response.headers, None)
    return dict(json.loads(data))


def plain(text: str) -> str:
    """A name reduced to lower-case words, so that spelling of case, hyphens and spaces does not matter."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def query_for(term: str) -> str:
    return _NAMING_WORDS.sub("", plain(term))


class IcdClient:
    """The WHO ICD API, version 2: client-credentials token, MMS search, an on-disk cache."""

    def __init__(
        self,
        settings: IcdSettings,
        cache_dir: Path = CACHE_DIR,
        fetch: Fetch = _fetch,
        pause: float = 0.2,
        retry_wait: float = 2.0,
    ) -> None:
        self._settings, self._fetch, self._pause, self._retry_wait = settings, fetch, pause, retry_wait
        self._cache, self._token, self.calls = cache_dir, "", 0

    def _headers(self) -> dict[str, str]:
        if not self._token:
            if not (self._settings.icd_api_client_id and self._settings.icd_api_client_secret):
                raise SystemExit("ICD_API_CLIENT_ID and ICD_API_CLIENT_SECRET are required (in .env, never in Git)")
            pair = f"{self._settings.icd_api_client_id}:{self._settings.icd_api_client_secret}".encode()
            reply = self._fetch(
                TOKEN_URL,
                {
                    "Authorization": "Basic " + base64.b64encode(pair).decode(),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "icdapi_access"}).encode(),
            )
            self._token = reply["access_token"]
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "API-Version": "v2",
            "Accept-Language": "en",
        }

    def get(self, url: str, cache_key: str) -> dict[str, Any]:
        path = self._cache / f"{hashlib.sha256(cache_key.encode()).hexdigest()[:32]}.json"
        if path.is_file():
            return dict(json.loads(path.read_text(encoding="utf-8")))
        reply = None
        for attempt in range(5):
            try:
                reply = self._fetch(url, self._headers(), None)
                break
            except urllib.error.HTTPError as error:
                if error.code == 401 and attempt == 0:
                    self._token = ""  # the token lasts about an hour
                elif error.code not in (429, 500, 502, 503, 504):
                    raise
                else:
                    time.sleep(self._retry_wait * (attempt + 1))
            except (http.client.HTTPException, OSError):  # the connection failed, not the request
                time.sleep(self._retry_wait * (attempt + 1))
        if reply is None:
            raise SystemExit(
                f"the ICD API could not be reached after 5 attempts ({cache_key}). Nothing is lost: answers already "
                "received are cached, so run the command again to continue"
            )
        self.calls += 1
        time.sleep(self._pause)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(reply), encoding="utf-8")
        return reply

    def release(self) -> str:
        latest = str(self.get(f"{API}/icd/release/11/mms", "mms")["latestRelease"])
        return latest.rstrip("/").split("/")[-2]

    def chapters(self, release: str) -> dict[str, str]:
        """Chapter code -> chapter title, for the release."""
        found = {}
        for uri in self.get(f"{API}/icd/release/11/{release}/mms", f"{release}/mms").get("child", []):
            chapter = self.get(uri.replace("http://", "https://"), uri)
            found[str(chapter.get("code", ""))] = str((chapter.get("title") or {}).get("@value", ""))
        return found

    def search(self, release: str, query: str) -> dict[str, Any]:
        params = {
            "q": query,
            "flatResults": "true",
            "useFlexisearch": "false",
            "highlightingEnabled": "false",
            "medicalCodingMode": "true",
        }
        return self.get(
            f"{API}/icd/release/11/{release}/mms/search?{urllib.parse.urlencode(params)}", f"{release}/search/{query}"
        )


def exact_matches(term: str, reply: dict[str, Any]) -> list[dict[str, Any]]:
    """Entities of a search reply that carry exactly the searched name, with where the name was found."""
    wanted, found = plain(term), []
    for entity in reply.get("destinationEntities", []):
        if plain(str(entity.get("title", ""))) == wanted:
            where = "title"
        else:
            where = next(
                (
                    str(pv.get("propertyId", "")).lower()
                    for pv in entity.get("matchingPVs", [])
                    if plain(str(pv.get("label", ""))) == wanted
                ),
                "",
            )
        if where and entity.get("theCode"):
            found.append(
                {
                    "code": entity["theCode"],
                    "title": entity.get("title", ""),
                    "uri": str(entity.get("id", "")),
                    "chapter": str(entity.get("chapter", "")),
                    "method": f"exact_{where}",
                    "residual": bool(entity.get("isResidualUnspecified") or entity.get("isResidualOther")),
                }
            )
    return found[:5]


def best_result(reply: dict[str, Any]) -> dict[str, Any] | None:
    entities = [e for e in reply.get("destinationEntities", []) if e.get("theCode")]
    if not entities:
        return None
    top = max(entities, key=lambda e: float(e.get("score") or 0))
    return {
        "code": top["theCode"],
        "title": top.get("title", ""),
        "score": round(float(top.get("score") or 0), 3),
        "chapter": str(top.get("chapter", "")),
    }


def link_id(subject: str, system: str, version: str, code: str) -> str:
    return "tl_" + hashlib.sha256("\x1f".join((subject, system, version, code)).encode()).hexdigest()[:24]


def loinc_table(raw_dir: Path, entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Active clinical LOINC terms from the supplied release, after its checksum is confirmed."""
    path = raw_dir / entry["name"]
    if not path.is_file():
        raise ArchiveError(f"{entry['name']}: missing from {raw_dir}")
    if sha256_file(path) != entry["sha256"]:
        raise ArchiveError(f"{entry['name']}: SHA-256 does not match the registered {entry['sha256']}")
    keep = ("LOINC_NUM", "SCALE_TYP", "SHORTNAME", "LONG_COMMON_NAME", "EXAMPLE_UCUM_UNITS")
    rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as release, release.open(entry["table"]) as raw:
        for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")):
            if row["STATUS"] == "ACTIVE" and row["CLASSTYPE"] == "2":
                # The whole name of the term, without a trailing bracket such as "[Presence]". The component
                # alone is not used: "Fever" is also the component of "Fever in Mother".
                name = plain(_BRACKET.sub("", row["LONG_COMMON_NAME"]))
                rows.append({**{k: row[k] for k in keep}, "name": name, "short": plain(row["SHORTNAME"])})
    return rows


def loinc_matches(text: str, kind: str, table: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """LOINC terms for one item: a term whose whole name is exactly the item's name, or, for a
    measurement question, a quantitative term whose one-word short name occurs in the question."""
    wanted, words = plain(text), set(plain(text).split())
    found = []
    for row in table:
        short = row["short"]
        if wanted == row["name"]:
            method = "exact_name"
        elif (
            kind == "measurement"
            and row["SCALE_TYP"] == "Qn"
            and len(short) >= 3
            and " " not in short
            and short in words
        ):
            method = "short_name_in_question"
        else:
            continue
        found.append(
            {
                "code": row["LOINC_NUM"],
                "title": row["LONG_COMMON_NAME"],
                "uri": f"https://loinc.org/{row['LOINC_NUM']}",
                "method": method,
                "units": row["EXAMPLE_UCUM_UNITS"],
            }
        )
    return found[:5]


def link_vocabularies(
    raw_dir: Path = RAW_DIR,
    database_url: str | None = None,
    client: IcdClient | None = None,
    loinc_entry: dict[str, Any] | None = None,
    source_ids: list[str] | None = None,
    progress: Callable[[str], None] = lambda _message: None,
) -> dict[str, Any]:
    """Look up every disease candidate and named feature term, and store the exact matches as pending links.

    source_ids limits the subjects to those mapped from these sources (used by tests); default all."""
    if database_url is None:
        app = Settings()
        database_url = app.migration_database_url or app.database_url
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL (or DATABASE_URL) is required")
    client = client or IcdClient(IcdSettings())
    release = client.release()
    chapters = client.chapters(release)
    table = loinc_table(raw_dir, loinc_entry) if loinc_entry else []
    scope = "AND m.source_id = ANY(%s)" if source_ids is not None else ""
    params: tuple[Any, ...] = (source_ids,) if source_ids is not None else ()
    engine = create_engine(database_url)
    items: list[dict[str, Any]] = []
    stored: Counter[str] = Counter()
    loinc_version = str(loinc_entry["version"]) if loinc_entry else ""
    try:
        with _raw_cursor(engine) as cur:  # a short read: the lookups below hold no database transaction open
            cur.execute(
                f"""SELECT DISTINCT d.disease_id, d.preferred_name FROM diseases d JOIN disease_mappings m USING (disease_id)
                    WHERE true {scope} ORDER BY 1""",  # noqa: S608 - fixed text
                params,
            )
            subjects = [("disease", row[0], row[1], "", "") for row in cur.fetchall()]
            cur.execute(
                f"""SELECT f.feature_id, f.preferred_name, f.kind::text,
                           max(m.original_term), max(m.transformation -> 'source_dictionary' ->> 'question')
                    FROM features f JOIN feature_mappings m USING (feature_id)
                    WHERE true {scope} GROUP BY 1, 2, 3 ORDER BY 1""",  # noqa: S608 - fixed text
                params,
            )
            for feature_id, name, kind, heading, question in cur.fetchall():
                subjects.append(
                    ("feature", feature_id, name, kind, question or ("" if not is_question(heading) else heading))
                )
        for number, (subject_type, subject_id, name, kind, question) in enumerate(subjects, start=1):
            if number % 100 == 0:
                progress(f"{number} of {len(subjects)} looked up, {client.calls} new API calls")
            item: dict[str, Any] = {
                "type": subject_type,
                "id": subject_id,
                "name": name,
                "kind": kind,
                "links": [],
                "best": None,
                "sent": "",
            }
            if not question:  # a name; a whole question sentence is not sent to the search
                item["sent"] = query_for(name)
                reply = client.search(release, item["sent"])
                item["best"] = best_result(reply)
                for match in exact_matches(item["sent"], reply):
                    detail = {
                        "query": item["sent"],
                        "chapter": match["chapter"],
                        "chapter_title": chapters.get(match["chapter"], ""),
                        "residual": match["residual"],
                    }
                    item["links"].append({**match, "system": ICD, "version": release, "detail": detail})
            if subject_type == "feature" and table:
                for match in loinc_matches(question or name, kind, table):
                    item["links"].append(
                        {**match, "system": LOINC, "version": loinc_version, "detail": {"units": match["units"]}}
                    )
            items.append(item)
        with _raw_cursor(engine) as cur:
            for item in items:
                for link in item["links"]:
                    cur.execute(
                        """INSERT INTO terminology_links (link_id, disease_id, feature_id, system, system_version, code, title,
                                                          uri, match_method, detail)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb) ON CONFLICT (link_id) DO NOTHING""",
                        (
                            link_id(item["id"], link["system"], link["version"], link["code"]),
                            item["id"] if item["type"] == "disease" else None,
                            item["id"] if item["type"] == "feature" else None,
                            link["system"],
                            link["version"],
                            link["code"],
                            link["title"],
                            link["uri"],
                            link["method"],
                            json.dumps(link["detail"], sort_keys=True),
                        ),
                    )
                    stored[link["system"]] += cur.rowcount
            cur.execute(
                "SELECT count(*), count(*) FILTER (WHERE status <> 'pending'), count(*) FILTER (WHERE uri IS NULL OR title = '') FROM terminology_links"
            )
            total, not_pending, incomplete = cur.fetchone()
    finally:
        engine.dispose()
    return {
        "release": release,
        "chapters": chapters,
        "items": items,
        "inserted": dict(stored),
        "api_calls": client.calls,
        "table": {"links": total, "not_pending": not_pending, "without_title_or_uri": incomplete},
    }


def summarise(result: dict[str, Any]) -> dict[str, Any]:
    """Counts for the report: how many items were looked up, how many found a name match."""
    rows: Counter[tuple[str, str]] = Counter()
    chapters: Counter[tuple[str, str]] = Counter()
    for item in result["items"]:
        group = item["type"] if item["type"] == "disease" else f"feature ({item['kind']})"
        icd = [link for link in item["links"] if link["system"] == ICD]
        if not item["sent"]:
            rows[(group, "not sent: a question sentence, not a name")] += 1
        elif icd:
            rows[(group, "name found in ICD-11")] += 1
            chapters[(group, icd[0]["detail"]["chapter"])] += 1
        elif item["best"]:
            rows[(group, "no entity with exactly this name")] += 1
        else:
            rows[(group, "no search result")] += 1
        if any(link["system"] == LOINC for link in item["links"]):
            rows[(group, "LOINC term found")] += 1
    return {"rows": rows, "chapters": chapters}


def check(result: dict[str, Any]) -> list[str]:
    diffs = []
    table = result["table"]
    if table["not_pending"]:
        diffs.append(f"{table['not_pending']} links are not pending; only a reviewer may decide a link")
    if table["without_title_or_uri"]:
        diffs.append(
            f"{table['without_title_or_uri']} links lack a title or a URI; the WHO terms require code, title and URI together"
        )
    for item in result["items"]:
        for link in item["links"]:
            if (
                link["system"] == ICD
                and plain(item["sent"]) not in {plain(link["title"])}
                and not link["method"].startswith("exact_")
            ):
                diffs.append(f"{item['name']}: a link that is not a name match")
    return diffs


def write_review(result: dict[str, Any], out_dir: Path = REVIEW_DIR) -> Path:
    """Every looked-up item with its links or its best search result. Kept outside Git."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "vocabulary_links.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "type",
                "id",
                "name",
                "kind",
                "sent",
                "system",
                "version",
                "code",
                "title",
                "uri",
                "match",
                "chapter",
                "best_code",
                "best_title",
                "best_score",
            ]
        )
        for item in result["items"]:
            best = item["best"] or {}
            tail = [best.get("code", ""), best.get("title", ""), best.get("score", "")]
            head = [item["type"], item["id"], item["name"], item["kind"], item["sent"]]
            if not item["links"]:
                writer.writerow([*head, "", "", "", "", "", "", "", *tail])
            for link in item["links"]:
                chapter = link["detail"].get("chapter", "")
                writer.writerow(
                    [
                        *head,
                        link["system"],
                        link["version"],
                        link["code"],
                        link["title"],
                        link["uri"],
                        link["method"],
                        chapter,
                        *tail,
                    ]
                )
    return path
