"""The identifiers of other vocabularies that MONDO lists for its terms: SNOMED CT and ICD-11 (M2.16).

Owner decision E62 (2026-11-18): the SNOMED CT and ICD-11 identifiers that MONDO carries are
imported as candidates, mapped correctly, and kept for the internal database only (E63: no code
of any vocabulary is shown to a user).

MONDO states for each identifier how it relates to its own term. Only an identifier it marks
`MONDO:equivalentTo`, and not as obsolete, may become a link; when it marks several identifiers
of one vocabulary as equivalent for one term, none is chosen. Everything else is listed with
MONDO's own marks for a person to judge.

- SNOMED CT: the concept identifier. The SNOMED CT release is not held, so no SNOMED name is
  known; the link shows the number and MONDO's name of the equivalent disease (owner, E62).
- ICD-11: MONDO gives the number of a foundation entity, which is not the kind of code a
  classification uses. WHO is asked for the entity's official title and for where it is coded in
  the MMS linearization. When the MMS entity is that same foundation entity, the link is its MMS
  code, the same kind M2.11 stores. When WHO codes it under another, broader entity, the link is
  the foundation entity itself and the broader MMS code is recorded beside it, not linked.

What leaves this machine: the foundation entity number, sent to the WHO ICD API. Never a label,
a case row or a count. This module reads one file and asks WHO; it touches no database.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .archives import ArchiveError, sha256_file
from .ontologies import OBO, _code, _release
from .vocabulary import API, IcdClient

SNOMED, ICD_FOUNDATION = "SNOMED CT", "ICD-11 Foundation"
PREFIXES = {"SCTID": SNOMED, "icd11.foundation": ICD_FOUNDATION}
EQUIVALENT = "MONDO:equivalentTo"
FOUNDATION_URI = "http://id.who.int/icd/entity/"
SNOMED_URI = "http://snomed.info/id/"

# Outcomes for one of our labels in one vocabulary. Only the first two store a link.
LINKED = "linked"
LINKED_FOUNDATION = "linked_to_the_foundation_entity"
SEVERAL = "several_identifiers_marked_equivalent"
NOT_EQUIVALENT = "no_identifier_marked_equivalent"
NONE_LISTED = "mondo_lists_no_identifier"
UNKNOWN_TO_WHO = "who_does_not_know_the_entity"

_RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
_OWL = "{http://www.w3.org/2002/07/owl#}"
_OIO = "{http://www.geneontology.org/formats/oboInOwl#}"


@dataclass(frozen=True)
class Identifier:
    vocabulary: str  # SNOMED CT or ICD-11 Foundation
    number: str  # as MONDO writes it, after the prefix
    marks: tuple[str, ...]  # MONDO's own marks on this identifier, such as MONDO:equivalentTo

    @property
    def equivalent(self) -> bool:
        return EQUIVALENT in self.marks and not any("obsolete" in mark.lower() for mark in self.marks)


def read_identifiers(
    raw_dir: Path, entry: dict[str, Any]
) -> tuple[str, dict[str, tuple[Identifier, ...]], dict[str, Any]]:
    """Release, the SNOMED CT and ICD-11 identifiers of every MONDO term, and what the file holds of them.

    The file is read only when its checksum and its release are the registered ones."""
    path = raw_dir / entry["name"]
    if not path.is_file():
        raise ArchiveError(f"{entry['name']}: missing from {raw_dir}")
    digest = sha256_file(path)
    if digest != entry["sha256"]:
        raise ArchiveError(f"{entry['name']}: SHA-256 {digest} does not match the registered {entry['sha256']}")
    listed: dict[str, list[str]] = {}
    marks: dict[tuple[str, str], set[str]] = {}
    version_iri, depth, root = "", 0, None
    try:
        for event, element in ET.iterparse(str(path), events=("start", "end")):
            if event == "start":
                root = element if root is None else root
                depth += 1
                continue
            depth -= 1
            if depth != 1:
                continue
            about = element.get(f"{_RDF}about", "")
            if element.tag == f"{_OWL}Ontology":
                found = element.find(f"{_OWL}versionIRI")
                version_iri = found.get(f"{_RDF}resource", "") if found is not None else ""
            elif element.tag == f"{_OWL}Class" and about.startswith(OBO + "MONDO_"):
                wanted = [
                    item.text
                    for item in element.findall(f"{_OIO}hasDbXref")
                    if item.text and item.text.split(":", 1)[0] in PREFIXES
                ]
                deprecated = (element.findtext(f"{_OWL}deprecated") or "") == "true"
                if wanted and not deprecated:
                    listed[_code(about)] = wanted
            elif element.tag == f"{_OWL}Axiom":
                source, target = element.find(f"{_OWL}annotatedSource"), element.find(f"{_OWL}annotatedTarget")
                text = (target.text or "") if target is not None else ""
                if source is not None and text.split(":", 1)[0] in PREFIXES:
                    given = {
                        item.text for item in element.findall(f"{_OIO}source") if (item.text or "").startswith("MONDO:")
                    }
                    marks.setdefault((_code(source.get(f"{_RDF}resource", "")), text), set()).update(given)
            if root is not None:
                root.clear()
    except ET.ParseError as error:
        raise ArchiveError(f"{path.name}: not a readable OWL file ({error})") from error
    version = _release(version_iri, path)
    if version != entry["version"]:
        raise ArchiveError(f"{entry['name']}: the file says release {version}, registered is {entry['version']}")
    identifiers = {
        code: tuple(
            Identifier(
                PREFIXES[text.split(":", 1)[0]], text.split(":", 1)[1], tuple(sorted(marks.get((code, text), ())))
            )
            for text in sorted(set(texts))
        )
        for code, texts in listed.items()
    }
    counted: dict[str, Any] = {"terms_with_an_identifier": len(identifiers)}
    for vocabulary in PREFIXES.values():
        of = [item for items in identifiers.values() for item in items if item.vocabulary == vocabulary]
        counted[vocabulary] = {
            "identifiers": len(of),
            "marked_equivalent": sum(item.equivalent for item in of),
            "other_marks": dict(
                Counter(mark for item in of if not item.equivalent for mark in (item.marks or ("no mark",)))
            ),
        }
    return version, identifiers, counted


def grade(
    identifiers: tuple[Identifier, ...], vocabulary: str
) -> tuple[str, Identifier | None, tuple[Identifier, ...]]:
    """(outcome, the one identifier MONDO marks equivalent or None, every identifier of the vocabulary)."""
    of = tuple(item for item in identifiers if item.vocabulary == vocabulary)
    equivalent = [item for item in of if item.equivalent]
    if len(equivalent) == 1:
        return LINKED, equivalent[0], of
    if equivalent:
        return SEVERAL, None, of
    return (NOT_EQUIVALENT if of else NONE_LISTED), None, of


def resolve_icd(client: IcdClient, release: str, number: str) -> dict[str, Any] | None:
    """WHO's official title of a foundation entity and where the MMS linearization codes it; None when WHO has no such entity.

    `same_entity` says the MMS entity is this very foundation entity, and not a broader one it is counted under."""
    uri = FOUNDATION_URI + number
    try:
        entity = client.get(f"{API}/icd/entity/{number}", f"entity/{number}")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    found: dict[str, Any] = {"title": str((entity.get("title") or {}).get("@value", "")), "uri": uri, "mms": None}
    try:
        query = urllib.parse.urlencode({"foundationUri": uri})
        coded = client.get(f"{API}/icd/release/11/{release}/mms/lookup?{query}", f"{release}/lookup/{number}")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        return found  # WHO knows the entity; the MMS linearization does not place it
    if coded.get("code"):
        found["mms"] = {
            "code": str(coded["code"]),
            "title": str((coded.get("title") or {}).get("@value", "")),
            "uri": str(coded.get("@id", "")),
            "same_entity": coded.get("source") == uri,
        }
    return found
