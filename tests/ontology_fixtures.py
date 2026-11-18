"""Two small invented vocabulary files in the forms of HPO (`hp.json`) and MONDO (`mondo.owl`).

Every term is made up ("synthetic glow", "pretend fever"); only the identifiers of the branch
roots are the real ones, because the reader checks them. Nothing here is medical content.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any

OBO = "http://purl.obolibrary.org/obo/"
HP_TYPE = OBO + "hp#"
ENTITY = "http://id.who.int/icd/entity/"


def _hp(number: str) -> str:
    return f"{OBO}HP_{number}"


def _node(number: str, label: str, synonyms: tuple[tuple[str, str, str], ...] = (), deprecated: bool = False) -> dict:
    meta: dict[str, Any] = {}
    if synonyms:
        meta["synonyms"] = [
            {"pred": pred, "val": text, **({"synonymType": HP_TYPE + kind} if kind else {})}
            for pred, text, kind in synonyms
        ]
    if deprecated:
        meta["deprecated"] = True
    return {"id": _hp(number), "lbl": label, "type": "CLASS", **({"meta": meta} if meta else {})}


def write_hpo(path: Path, release: str = "2026-01-01", tag: str = "", frequency_label: str = "Frequency") -> Path:
    """A file with 13 terms (1 obsolete) and one entry that is not a term. `tag` is appended to every invented name."""
    t = f" {tag}" if tag else ""
    nodes = [
        _node("0000001", "All"),
        _node("0000118", "Phenotypic abnormality"),
        _node("0000005", "Mode of inheritance"),
        _node("0040279", frequency_label),
        _node(
            "9000001",
            f"Synthetic glow{t}",
            (
                ("hasExactSynonym", f"Shining skin{t}", "layperson"),
                ("hasExactSynonym", f"SG{t}", "abbreviation"),
                ("hasRelatedSynonym", f"Brightness{t}", ""),
            ),
        ),
        _node("9000002", f"Synthetic hum{t}", (("hasExactSynonym", f"Humming{t}", ""),)),
        _node("9000003", f"obsolete Synthetic fog{t}", deprecated=True),
        _node("9000004", f"Very often{t}"),
        _node("9000005", f"Synthetic twin one{t}", (("hasExactSynonym", f"Twin sign{t}", ""),)),
        _node("9000006", f"Synthetic twin two{t}", (("hasExactSynonym", f"Twin sign{t}", ""),)),
        _node("9000007", f"Twin mark{t}"),
        _node("9000008", f"Synthetic other{t}", (("hasExactSynonym", f"Twin mark{t}", ""),)),
        _node("9000009", f"Synthetic glow of the left hand{t}"),
        {"id": OBO + "RO_0002314", "lbl": "characteristic of part of", "type": "PROPERTY"},
    ]
    children = {
        "0000001": ("0000118", "0000005", "0040279"),
        "0000118": ("9000001", "9000005", "9000006", "9000007", "9000008", "9000009"),
        "9000001": ("9000002",),
        "0040279": ("9000004",),
    }
    edges = [
        {"sub": _hp(child), "pred": "is_a", "obj": _hp(parent)} for parent, kids in children.items() for child in kids
    ]
    graph = {
        "id": OBO + "hp.json",
        "meta": {"version": f"{OBO}hp/releases/{release}/hp.json"},
        "nodes": nodes,
        "edges": edges,
    }
    path.write_text(json.dumps({"graphs": [graph]}), encoding="utf-8")
    return path


_HEAD = """<?xml version="1.0"?>
<rdf:RDF xmlns="http://purl.obolibrary.org/obo/mondo.owl#"
     xmlns:obo="http://purl.obolibrary.org/obo/"
     xmlns:owl="http://www.w3.org/2002/07/owl#"
     xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
     xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
     xmlns:oboInOwl="http://www.geneontology.org/formats/oboInOwl#">
    <owl:Ontology rdf:about="http://purl.obolibrary.org/obo/mondo.owl">
        <owl:versionIRI rdf:resource="http://purl.obolibrary.org/obo/mondo/releases/{release}/mondo.owl"/>
    </owl:Ontology>
    <owl:AnnotationProperty rdf:about="http://purl.obolibrary.org/obo/OMO_0003005">
        <rdfs:label>UK spelling synonym</rdfs:label>
    </owl:AnnotationProperty>
    <owl:AnnotationProperty rdf:about="http://purl.obolibrary.org/obo/mondo#ABBREVIATION">
        <rdfs:label>abbreviation</rdfs:label>
    </owl:AnnotationProperty>
"""


def _class(number: str, label: str, parents: tuple[str, ...] = (), body: str = "") -> str:
    lines = [f'    <owl:Class rdf:about="{OBO}MONDO_{number}">']
    lines += [f'        <rdfs:subClassOf rdf:resource="{OBO}MONDO_{parent}"/>' for parent in parents]
    lines += [body] if body else []
    lines += [f'        <rdfs:label xml:lang="en">{label}</rdfs:label>', "    </owl:Class>"]
    return "\n".join(lines) + "\n"


def _synonym(kind: str, text: str) -> str:
    return f"        <oboInOwl:has{kind}Synonym>{text}</oboInOwl:has{kind}Synonym>"


def _typed(number: str, text: str, type_iri: str) -> str:
    return f"""    <owl:Axiom>
        <owl:annotatedSource rdf:resource="{OBO}MONDO_{number}"/>
        <owl:annotatedProperty rdf:resource="http://www.geneontology.org/formats/oboInOwl#hasExactSynonym"/>
        <owl:annotatedTarget>{text}</owl:annotatedTarget>
        <oboInOwl:hasSynonymType rdf:resource="{type_iri}"/>
    </owl:Axiom>
"""


def _xref(text: str) -> str:
    return f"        <oboInOwl:hasDbXref>{text}</oboInOwl:hasDbXref>"


def _marked(number: str, text: str, *sources: str) -> str:
    lines = "".join(f"        <oboInOwl:source>{source}</oboInOwl:source>\n" for source in sources)
    return f"""    <owl:Axiom>
        <owl:annotatedSource rdf:resource="{OBO}MONDO_{number}"/>
        <owl:annotatedProperty rdf:resource="http://www.geneontology.org/formats/oboInOwl#hasDbXref"/>
        <owl:annotatedTarget>{text}</owl:annotatedTarget>
{lines}    </owl:Axiom>
"""


def write_mondo(path: Path, release: str = "2026-01-01", tag: str = "", human_label: str = "human disease") -> Path:
    """A file with 12 MONDO terms (1 obsolete) and one class of another vocabulary.

    Four current terms list identifiers of other vocabularies (invented numbers), with MONDO's kind of marks:
    9000001 one SNOMED CT and one ICD-11 identifier marked equivalent, and a related SNOMED CT one;
    9000003 two SNOMED CT identifiers both marked equivalent, and an ICD-11 one marked broader;
    9000006 an ICD-11 identifier marked equivalent, and a SNOMED CT one equivalent to an obsolete concept;
    9000002 (a disease of dogs) one SNOMED CT identifier. The obsolete term's identifier is not read."""
    t = f" {tag}" if tag else ""
    restriction = """        <rdfs:subClassOf>
            <owl:Restriction>
                <owl:onProperty rdf:resource="http://purl.obolibrary.org/obo/RO_0004003"/>
                <owl:someValuesFrom rdf:resource="http://purl.obolibrary.org/obo/MONDO_0005583"/>
            </owl:Restriction>
        </rdfs:subClassOf>"""
    fever = "\n".join(
        [
            restriction,  # a parent that is not a plain link is ignored: this term is not an animal disease
            _synonym("Exact", f"pretend fever{t}"),
            _synonym("Exact", f"SFD{t}"),
            _synonym("Exact", f"synthetic foever disease{t}"),
            _synonym("Narrow", f"mild pretend fever{t}"),
            _xref("MESH:D000001"),
            _xref("SCTID:111"),
            _xref("SCTID:112"),
            _xref("icd11.foundation:900001"),
        ]
    )
    parts = [
        _HEAD.format(release=release),
        _class("0000001", "disease"),
        _class("0700096", human_label, ("0000001",)),
        _class("0005583", "non-human animal disease", ("0000001",)),
        _class("0021178", "injury"),
        _class("0042489", "disease susceptibility"),
        _class("0021125", "disease characteristic"),
        _class("9000001", f"synthetic fever disease{t}", ("0700096",), fever),
        _typed("9000001", f"SFD{t}", OBO + "mondo#ABBREVIATION"),
        _typed("9000001", f"synthetic foever disease{t}", OBO + "OMO_0003005"),
        _marked("9000001", "MESH:D000001", "MONDO:equivalentTo"),
        _marked("9000001", "SCTID:111", "DOID:1", "MONDO:equivalentTo"),
        _marked("9000001", "SCTID:112", "MONDO:relatedTo"),
        _marked("9000001", "icd11.foundation:900001", "MONDO:equivalentTo"),
        _class(
            "9000002",
            f"synthetic fever disease{t}, dog",
            ("0005583",),
            _synonym("Exact", f"pretend fever{t}") + "\n" + _xref("SCTID:115"),
        ),
        _marked("9000002", "SCTID:115", "MONDO:equivalentTo"),
        _class(
            "9000003",
            f"synthetic cut{t}",
            ("0021178",),
            "\n".join((_xref("SCTID:113"), _xref("SCTID:114"), _xref("icd11.foundation:900003"))),
        ),
        _marked("9000003", "SCTID:113", "MONDO:equivalentTo"),
        _marked("9000003", "SCTID:114", "MONDO:equivalentTo"),
        _marked("9000003", "icd11.foundation:900003", "MONDO:mondoIsBroaderThanSource"),
        _class("9000004", f"synthetic leaning{t}", ("0042489",)),
        _class(
            "9000005",
            f"obsolete synthetic ache{t}",
            body='        <owl:deprecated rdf:datatype="http://www.w3.org/2001/XMLSchema#boolean">true</owl:deprecated>\n'
            + _xref("SCTID:117"),
        ),
        _marked("9000005", "SCTID:117", "MONDO:equivalentTo"),
        _class(
            "9000006",
            f"synthetic fever disease{t} of the young",
            ("9000001",),
            _xref("SCTID:116") + "\n" + _xref("icd11.foundation:900006"),
        ),
        _marked("9000006", "SCTID:116", "MONDO:equivalentObsolete"),
        _marked("9000006", "icd11.foundation:900006", "MONDO:equivalentTo"),
        f'    <owl:Class rdf:about="{OBO}HP_0000118">\n        <rdfs:label>Phenotypic abnormality</rdfs:label>\n    </owl:Class>\n',
        "</rdf:RDF>\n",
    ]
    path.write_text("".join(parts), encoding="utf-8")
    return path


def entry(path: Path, kind: str, release: str = "2026-01-01") -> dict[str, Any]:
    """The registry entry a file would have in `specs/supplementary_sources.json`."""
    return {
        "name": path.name,
        "kind": kind,
        "version": release,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


class FakeWho:
    """Answers like the WHO ICD API v2 for foundation entities and the MMS lookup, from a table.

    entities: number -> (title, None) or (title, (mms code, mms title, number of the foundation entity it is coded as))."""

    def __init__(self, entities):
        self.entities, self.seen = entities, []

    def __call__(self, url, headers, body):
        if "connect/token" in url:
            return {"access_token": "token-1", "token_type": "Bearer", "expires_in": 3600}
        assert headers["API-Version"] == "v2" and headers["Accept-Language"] == "en"
        self.seen.append(url)
        parts = urllib.parse.urlsplit(url)
        if parts.path == "/icd/release/11/mms":
            return {"latestRelease": "http://id.who.int/icd/release/11/2026-01/mms"}
        if parts.path.startswith("/icd/entity/"):
            number = parts.path.rsplit("/", 1)[1]
            if number not in self.entities:
                raise urllib.error.HTTPError(url, 404, "Not Found", None, None)  # type: ignore[arg-type]
            return {"@id": ENTITY + number, "title": {"@language": "en", "@value": self.entities[number][0]}}
        assert parts.path == "/icd/release/11/2026-01/mms/lookup"
        (uri,) = urllib.parse.parse_qs(parts.query)["foundationUri"]
        coded = self.entities[uri.rsplit("/", 1)[1]][1]
        if coded is None:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)  # type: ignore[arg-type]
        code, title, source = coded
        return {
            "@id": f"http://id.who.int/icd/release/11/2026-01/mms/{source}",
            "code": code,
            "title": {"@language": "en", "@value": title},
            "source": ENTITY + source,
            "classKind": "category",
        }
