"""Candidate provider boundary.

The only implementation matches reviewer-authored candidate conditions from the loaded
bundle. No statistical model is wired in: the archive-11 baseline scored below the majority
comparator and is rejected for serving. Scores are never exposed to callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from feeltriva_clinical.bundle import ReleaseBundle
from feeltriva_clinical.rules import Facts, evaluate, referenced_features


@dataclass(frozen=True)
class CandidateMatch:
    disease_id: str
    name: str
    explanation: str
    evidence_ids: tuple[str, ...]
    supporting_features: tuple[str, ...]
    conflicting_features: tuple[str, ...]


class CandidateProvider(Protocol):
    def candidates(self, confirmed: Facts) -> list[CandidateMatch]: ...


class BundleCandidateProvider:
    def __init__(self, bundle: ReleaseBundle, *, clinical_mode: bool) -> None:
        self._defs = [c for c in bundle.candidates if not clinical_mode or c.status == "approved"]

    def candidates(self, confirmed: Facts) -> list[CandidateMatch]:
        out = []
        for c in self._defs:
            if evaluate(c.condition_ast, confirmed) is not True:
                continue
            refs = list(dict.fromkeys(referenced_features(c.condition_ast)))
            out.append(
                CandidateMatch(
                    c.disease_id,
                    c.name,
                    c.explanation,
                    tuple(c.evidence_ids),
                    tuple(f for f in refs if confirmed.presence.get(f) == "present"),
                    tuple(f for f in refs if confirmed.presence.get(f) == "absent"),
                )
            )
        return out
