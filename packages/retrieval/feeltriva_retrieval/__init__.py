"""Evidence lookup boundary. Only a bundle-backed provider exists; no vector search yet."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from feeltriva_clinical.bundle import ReleaseBundle


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    source_title: str
    source_url: str | None
    excerpt: str
    knowledge_release: str


class EvidenceProvider(Protocol):
    def get_many(self, evidence_ids: list[str]) -> dict[str, EvidenceRecord]: ...


class BundleEvidenceProvider:
    """Serves evidence that exists in the loaded release. Unknown IDs are simply not returned;
    callers must treat a missing citation as 'no evidence' and withhold the claim."""

    def __init__(self, bundle: ReleaseBundle, *, clinical_mode: bool) -> None:
        self._release = bundle.knowledge_version
        self._items = {e.evidence_id: e for e in bundle.evidence if not clinical_mode or e.status == "approved"}

    def get_many(self, evidence_ids: list[str]) -> dict[str, EvidenceRecord]:
        return {
            i: EvidenceRecord(i, e.source_title, e.source_url, e.excerpt, self._release)
            for i in evidence_ids
            if (e := self._items.get(i)) is not None
        }
