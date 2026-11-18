"""Two open vocabularies read from the files the owner supplied: HPO and MONDO (M2.14).

HPO (Human Phenotype Ontology) names symptoms, signs and findings; MONDO names diseases. They
are used in place of SNOMED CT, which could not be obtained (decisions D-T1, E59, E60).

This module reads the two files and answers one question about a name of ours: which term, if
any, carries exactly this name. The rule is that of M2.11, made stricter by what the files show:

- a term is linked only when our whole name equals its label or one of its exact synonyms;
- an abbreviation is not a name. Our label "scar" equals SCAR, MONDO's abbreviation of "severe
  cutaneous adverse reaction", and our symptom "cold" equals COLD, its abbreviation of a lung
  disease. A name that matches only an abbreviation gets no link;
- a related, broad or narrow synonym never gives a link;
- an obsolete term, a disease of non-human animals and a term outside the branches that describe
  a person's condition never give a link;
- when several terms carry the name, none is chosen.

A name without a link gets a stated reason and the nearest terms, for a person to judge. The
identifiers of other vocabularies that the files carry (ICD, SNOMED CT, UMLS and others) are not
read (decisions E56, D-T2).

This module reads two files and no database.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .archives import ArchiveError, sha256_file
from .relations import content_words
from .vocabulary import plain, query_for

HPO, MONDO = "HPO", "MONDO"
KINDS = {"hpo_release": HPO, "mondo_release": MONDO}
OBO = "http://purl.obolibrary.org/obo/"
LABEL, EXACT = "label", "exact_synonym"
_LOOSE = {
    "hasRelatedSynonym": "related_synonym",
    "hasBroadSynonym": "broad_synonym",
    "hasNarrowSynonym": "narrow_synonym",
}
# Synonym types, as the vocabularies mark them themselves, that are not a name of the term.
NOT_A_NAME = frozenset({"abbreviation", "ambiguous", "non_human"})
_RELEASE = re.compile(r"/releases/([^/]+)/")
_OBSOLETE = re.compile(r"^obsolete\s+", re.IGNORECASE)

# HPO: the two branches under its root that say how a finding is inherited or how often it
# occurs, not what a person has. Checked against their labels when the file is read.
HPO_ROOT = "HP:0000001"
HPO_NOT_FINDINGS = {"HP:0000005": "Mode of inheritance", "HP:0040279": "Frequency"}
# MONDO: its branch roots, checked against their labels when the file is read.
MONDO_BRANCHES = {
    "MONDO:0700096": "human disease",
    "MONDO:0005583": "non-human animal disease",
    "MONDO:0021178": "injury",
    "MONDO:0042489": "disease susceptibility",
    "MONDO:0021125": "disease characteristic",
}
MONDO_LINKABLE, MONDO_NEVER = frozenset({"human disease", "injury"}), "non-human animal disease"

CLOSE_ENOUGH, MAX_CANDIDATES = 0.5, 3  # share of words in common for a "nearest term"; how many are listed

# Outcomes of a lookup. Only LINKED stores a link.
LINKED = "linked"
SEVERAL = "several_terms_carry_the_name"
ABBREVIATION_ONLY = "matches_only_an_abbreviation"
LOOSER_ONLY = "matches_only_a_looser_synonym"
NOT_LINKABLE = "only_terms_that_are_not_linkable"
NEAREST = "no_term_with_this_name_nearest_listed"
NOTHING = "no_term_with_this_name_or_near_it"
SENTENCE = "not_looked_up_a_question_sentence"

_RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
_RDFS = "{http://www.w3.org/2000/01/rdf-schema#}"
_OWL = "{http://www.w3.org/2002/07/owl#}"
_OIO = "{http://www.geneontology.org/formats/oboInOwl#}"


@dataclass(frozen=True)
class Name:
    text: str  # as the file writes it
    how: str  # label, exact_synonym, related_synonym, broad_synonym or narrow_synonym
    kind: str = ""  # the vocabulary's own type of the synonym: abbreviation, layperson, ...


@dataclass(frozen=True)
class Term:
    code: str
    label: str
    uri: str
    synonyms: tuple[Name, ...]
    parents: tuple[str, ...]
    obsolete: bool


@dataclass
class Vocabulary:
    system: str
    version: str
    terms: dict[str, Term]  # every term of the file, current and obsolete
    branch: dict[str, str]  # term code -> the branch it stands in ("obsolete" for an obsolete term)
    linkable: frozenset[str]  # codes of the terms that may be linked
    inventory: dict[str, Any]  # what the file holds, counted, so that nothing in it goes unaccounted
    names: dict[str, list[tuple[str, Name]]] = field(default_factory=dict, repr=False)
    words: dict[str, list[tuple[str, Name, frozenset[str]]]] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class Candidate:
    code: str
    title: str
    uri: str
    how: str
    matched: str  # the label or synonym, as the file writes it, that was compared with our name
    kind: str
    branch: str
    note: str = ""


@dataclass(frozen=True)
class Outcome:
    outcome: str
    reason: str = ""
    link: Candidate | None = None
    candidates: tuple[Candidate, ...] = ()


def not_a_name(kind: str) -> bool:
    return any(part in NOT_A_NAME for part in kind.split("+"))


def _code(iri: str) -> str:
    """`http://purl.obolibrary.org/obo/HP_0001251` -> `HP:0001251`."""
    return iri.rsplit("/", 1)[-1].replace("_", ":", 1)


def _type_name(iri: str, labels: dict[str, str]) -> str:
    if not iri:
        return ""
    if "#" in iri:
        return iri.rsplit("#", 1)[-1].lower()
    return (labels.get(iri) or iri.rsplit("/", 1)[-1]).lower()


def _release(iri: str, path: Path) -> str:
    found = _RELEASE.search(iri)
    if not found:
        raise ArchiveError(f"{path.name}: no release date in its version address {iri!r}")
    return found.group(1)


def _branches(terms: dict[str, Term], tops: dict[str, str]) -> dict[str, frozenset[str]]:
    """For every current term, the named branch roots it stands under (itself included)."""
    known: dict[str, frozenset[str]] = {}

    def of(code: str) -> frozenset[str]:
        stack, opened = [(code, False)], set()
        while stack:  # every parent is settled before its child, without recursion
            current, parents_done = stack.pop()
            if current in known:
                continue
            if parents_done:
                found = {tops[current]} if current in tops else set()
                for parent in terms[current].parents:
                    found |= known.get(parent, frozenset())
                known[current] = frozenset(found)
            elif current not in opened:  # a term is opened once, so a loop in the file cannot hang the reader
                opened.add(current)
                stack.append((current, True))
                stack.extend((parent, False) for parent in terms[current].parents if parent in terms)
        return known[code]

    return {code: of(code) for code, term in terms.items() if not term.obsolete}


def _finish(
    system: str,
    version: str,
    terms: dict[str, Term],
    branch: dict[str, str],
    linkable: frozenset[str],
    entries: int,
) -> Vocabulary:
    current = [term for term in terms.values() if not term.obsolete]
    synonyms = [name for term in current for name in term.synonyms]
    inventory = {
        "entries_in_file": entries,
        "terms": len(terms),
        "entries_of_other_vocabularies": entries - len(terms),
        "current": len(current),
        "obsolete": len(terms) - len(current),
        "by_branch": dict(Counter(branch[term.code] for term in current)),
        "linkable": len(linkable),
        "labels": len(current),
        "exact_synonyms": sum(1 for name in synonyms if name.how == EXACT),
        "looser_synonyms": sum(1 for name in synonyms if name.how != EXACT),
        "synonyms_that_are_not_names": sum(1 for name in synonyms if name.how == EXACT and not_a_name(name.kind)),
        "parent_links": sum(len(term.parents) for term in terms.values()),
    }
    vocabulary = Vocabulary(system, version, terms, branch, linkable, inventory)
    for term in terms.values():
        label = Name(_OBSOLETE.sub("", term.label) if term.obsolete else term.label, LABEL)
        for name in (label, *term.synonyms):
            vocabulary.names.setdefault(plain(name.text), []).append((term.code, name))
            if term.code in linkable and not not_a_name(name.kind):
                words = content_words(name.text)
                for word in words:
                    vocabulary.words.setdefault(word, []).append((term.code, name, words))
    return vocabulary


def read_hpo(path: Path) -> Vocabulary:
    """Every term of an HPO release in its JSON form (`hp.json`)."""
    try:
        graph = json.loads(path.read_text(encoding="utf-8"))["graphs"][0]
        nodes, edges = graph["nodes"], graph["edges"]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ArchiveError(f"{path.name}: not an HPO file in the expected JSON form ({error})") from error
    version = _release(str(graph.get("meta", {}).get("version", "")), path)
    parents: dict[str, list[str]] = {}
    for edge in edges:
        if edge.get("pred") == "is_a":
            parents.setdefault(_code(str(edge["sub"])), []).append(_code(str(edge["obj"])))
    terms: dict[str, Term] = {}
    for node in nodes:
        iri = str(node.get("id", ""))
        if not iri.startswith(OBO + "HP_") or node.get("type") != "CLASS":
            continue
        meta = node.get("meta") or {}
        synonyms = tuple(
            Name(
                str(synonym.get("val", "")),
                EXACT
                if synonym.get("pred") == "hasExactSynonym"
                else _LOOSE.get(synonym.get("pred"), "related_synonym"),
                _type_name(str(synonym.get("synonymType", "")), {}),
            )
            for synonym in meta.get("synonyms", [])
        )
        code = _code(iri)
        terms[code] = Term(
            code,
            str(node.get("lbl", "")),
            iri,
            synonyms,
            tuple(sorted(parents.get(code, []))),
            bool(meta.get("deprecated")),
        )
    for code, label in {HPO_ROOT: "All", **HPO_NOT_FINDINGS}.items():
        if code not in terms or terms[code].label != label:
            raise ArchiveError(f"{path.name}: {code} is not {label!r}; the layout of the file has changed")
    tops = {code: term.label for code, term in terms.items() if HPO_ROOT in term.parents and not term.obsolete}
    excluded = set(HPO_NOT_FINDINGS.values())
    branch, linkable = {}, set()
    for code, found in _branches(terms, tops).items():
        branch[code] = " + ".join(sorted(found)) or "root"
        if found - excluded:
            linkable.add(code)
    branch.update({code: "obsolete" for code, term in terms.items() if term.obsolete})
    return _finish(HPO, version, terms, branch, frozenset(linkable), len(nodes))


def read_mondo(path: Path) -> Vocabulary:
    """Every MONDO term of a MONDO release in its OWL form (`mondo.owl`), read as a stream.

    The file also holds classes of other vocabularies that MONDO refers to; they are counted and
    not read. The caller has already confirmed the file's SHA-256 against the registered one."""
    raw: dict[str, tuple[str, list[tuple[str, str]], list[str], bool]] = {}
    typed: dict[tuple[str, str], set[str]] = {}
    type_labels: dict[str, str] = {}
    version_iri, classes, depth, root = "", 0, 0, None
    properties = (("hasExactSynonym", EXACT), *_LOOSE.items())
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
            elif element.tag == f"{_OWL}AnnotationProperty":
                type_labels[about] = element.findtext(f"{_RDFS}label") or ""
            elif element.tag == f"{_OWL}Class":
                classes += 1
                if about.startswith(OBO + "MONDO_"):
                    raw[about] = (
                        element.findtext(f"{_RDFS}label") or "",
                        [(item.text or "", how) for tag, how in properties for item in element.findall(f"{_OIO}{tag}")],
                        [
                            parent
                            for item in element.findall(f"{_RDFS}subClassOf")
                            if (parent := item.get(f"{_RDF}resource", "")).startswith(OBO + "MONDO_")
                        ],
                        (element.findtext(f"{_OWL}deprecated") or "") == "true",
                    )
            elif element.tag == f"{_OWL}Axiom":
                types = [item.get(f"{_RDF}resource", "") for item in element.findall(f"{_OIO}hasSynonymType")]
                source, target = element.find(f"{_OWL}annotatedSource"), element.find(f"{_OWL}annotatedTarget")
                if types and source is not None and target is not None:
                    typed.setdefault((source.get(f"{_RDF}resource", ""), target.text or ""), set()).update(types)
            if root is not None:
                root.clear()  # keep memory flat: the file is 255 MB
    except ET.ParseError as error:
        raise ArchiveError(f"{path.name}: not a readable OWL file ({error})") from error
    version = _release(version_iri, path)
    terms: dict[str, Term] = {}
    for iri, (label, synonyms, parents, obsolete) in raw.items():
        names = tuple(
            Name(text, how, "+".join(sorted(_type_name(kind, type_labels) for kind in typed.get((iri, text), ()))))
            for text, how in synonyms
        )
        code = _code(iri)
        terms[code] = Term(code, label, iri, names, tuple(sorted(_code(parent) for parent in parents)), obsolete)
    for code, label in MONDO_BRANCHES.items():
        if code not in terms or terms[code].label != label:
            raise ArchiveError(f"{path.name}: {code} is not {label!r}; the layout of the file has changed")
    order = list(MONDO_BRANCHES.values())
    branch, linkable = {}, set()
    for code, found in _branches(terms, MONDO_BRANCHES).items():
        branch[code] = " + ".join(name for name in order if name in found) or "disease, no narrower branch"
        if MONDO_NEVER not in found and found & MONDO_LINKABLE:
            linkable.add(code)
    branch.update({code: "obsolete" for code, term in terms.items() if term.obsolete})
    return _finish(MONDO, version, terms, branch, frozenset(linkable), classes)


def read_vocabulary(raw_dir: Path, entry: dict[str, Any]) -> Vocabulary:
    """The registered file, read only after its checksum is confirmed; its release must be the registered one."""
    path = raw_dir / entry["name"]
    if not path.is_file():
        raise ArchiveError(f"{entry['name']}: missing from {raw_dir}")
    digest = sha256_file(path)
    if digest != entry["sha256"]:
        raise ArchiveError(f"{entry['name']}: SHA-256 {digest} does not match the registered {entry['sha256']}")
    vocabulary = read_hpo(path) if KINDS[entry["kind"]] == HPO else read_mondo(path)
    if vocabulary.version != entry["version"]:
        raise ArchiveError(
            f"{entry['name']}: the file says release {vocabulary.version}, registered is {entry['version']}"
        )
    return vocabulary


def _candidate(vocabulary: Vocabulary, code: str, name: Name, note: str = "") -> Candidate:
    term = vocabulary.terms[code]
    return Candidate(code, term.label, term.uri, name.how, name.text, name.kind, vocabulary.branch.get(code, ""), note)


def _unique(vocabulary: Vocabulary, hits: list[tuple[str, Name]], note: str = "") -> tuple[Candidate, ...]:
    seen: dict[str, Candidate] = {}
    for code, name in hits:
        seen.setdefault(code, _candidate(vocabulary, code, name, note))
    return tuple(seen[code] for code in sorted(seen))


def nearest(vocabulary: Vocabulary, wanted: str) -> tuple[Candidate, ...]:
    """Up to three linkable terms one of whose names shares at least half of its words with ours."""
    words = content_words(wanted)
    if not words:
        return ()
    # A name that shares half of our words holds at least one of our (n // 2 + 1) rarest words.
    postings = sorted((vocabulary.words.get(word, []) for word in words), key=len)[: len(words) // 2 + 1]
    best: dict[str, tuple[float, Name]] = {}
    for posting in postings:
        for code, name, theirs in posting:
            score = len(words & theirs) / len(words | theirs)
            if score >= CLOSE_ENOUGH and score > best.get(code, (0.0, name))[0]:
                best[code] = (score, name)
    ranked = sorted(best.items(), key=lambda item: (-item[1][0], vocabulary.terms[item[0]].label, item[0]))
    return tuple(
        _candidate(vocabulary, code, name, f"{score:.2f} of the words in common")
        for code, (score, name) in ranked[:MAX_CANDIDATES]
    )


def lookup(vocabulary: Vocabulary, name: str) -> Outcome:
    """The term that carries exactly this name, or the reason there is none and the nearest terms."""
    wanted = query_for(name)
    hits = vocabulary.names.get(wanted, [])
    usable = [(code, found) for code, found in hits if code in vocabulary.linkable]
    names = [(code, found) for code, found in usable if found.how in (LABEL, EXACT) and not not_a_name(found.kind)]
    by_label = sorted({code for code, found in names if found.how == LABEL})
    by_name = sorted({code for code, _found in names})
    chosen = by_label[0] if len(by_label) == 1 else by_name[0] if not by_label and len(by_name) == 1 else ""
    if chosen:
        found = next(found for code, found in names if code == chosen and (found.how == LABEL or not by_label))
        others = [code for code in by_name if code != chosen]
        note = f"also listed as a synonym of {', '.join(others)}" if others else ""
        return Outcome(LINKED, "", _candidate(vocabulary, chosen, found, note))
    if by_name:
        return Outcome(
            SEVERAL, f"{len(by_name)} terms carry this name; a person chooses", candidates=_unique(vocabulary, names)
        )
    marked = [(code, found) for code, found in usable if found.how == EXACT and not_a_name(found.kind)]
    if marked:
        kinds = ", ".join(sorted({found.kind.replace("_", " ") for _code_, found in marked}))
        return Outcome(
            ABBREVIATION_ONLY,
            f"the name equals only a synonym the vocabulary marks as {kinds}; that is not a name of the term",
            candidates=_unique(vocabulary, marked),
        )
    looser = [(code, found) for code, found in usable if found.how not in (LABEL, EXACT)]
    if looser:
        return Outcome(
            LOOSER_ONLY,
            "the name equals only a related, broad or narrow synonym, which does not say the term means the same",
            candidates=_unique(vocabulary, looser),
        )
    if hits:
        where = ", ".join(sorted({vocabulary.branch.get(code, "") for code, _found in hits}))
        return Outcome(
            NOT_LINKABLE,
            f"the only terms with this name are not linkable ({where})",
            candidates=_unique(vocabulary, hits),
        )
    close = nearest(vocabulary, wanted)
    if close:
        return Outcome(NEAREST, "no term carries this name; the nearest by shared words are listed", candidates=close)
    return Outcome(NOTHING, "no term carries this name or shares half of its words")
