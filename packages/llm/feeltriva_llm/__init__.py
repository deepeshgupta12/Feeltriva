"""Provider boundary for structured extraction. Only a deterministic mock is implemented.

No external model provider is called. A real adapter must implement `Extractor`, return
exact text spans and concept IDs from the supplied vocabulary, and raise `ExtractionError`
on timeout, malformed output or refusal (which the service turns into an incomplete state).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


class ExtractionError(RuntimeError):
    pass


@dataclass(frozen=True)
class VocabularyTerm:
    feature_id: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class ExtractedObservation:
    feature_id: str | None
    start: int
    end: int
    text: str
    presence: str  # present | absent | uncertain
    experiencer: str = "self"


@dataclass(frozen=True)
class ExtractionResult:
    observations: tuple[ExtractedObservation, ...]
    extractor_version: str


class Extractor(Protocol):
    version: str

    def extract(self, message: str, vocabulary: list[VocabularyTerm]) -> ExtractionResult: ...


_UNCERTAIN = re.compile(r"\b(maybe|might|possibly|perhaps|not sure|unsure)\b[^.;,!?]*$", re.I)
_NEGATED = re.compile(r"\b(no|not|without|never|don't have|do not have|didn't have)\b[^.;,!?]*$", re.I)


class MockExtractor:
    """Keyword matcher over the supplied vocabulary. Exercises workflow only.

    It never invents a negative: a term is 'absent' only when an explicit negation cue
    precedes it in the same clause. Text matching no vocabulary term is returned as a
    single unmapped, uncertain observation so nothing the user wrote is silently dropped.
    """

    version = "fixture-extractor-0"

    def extract(self, message: str, vocabulary: list[VocabularyTerm]) -> ExtractionResult:
        found: dict[str, ExtractedObservation] = {}
        for term in vocabulary:
            for alias in term.aliases:
                for m in re.finditer(rf"(?<![\w-]){re.escape(alias)}(?![\w-])", message, re.I):
                    clause = message[: m.start()]
                    if _UNCERTAIN.search(clause):
                        presence = "uncertain"
                    elif _NEGATED.search(clause):
                        presence = "absent"
                    else:
                        presence = "present"
                    prior = found.get(term.feature_id)
                    if prior is None or m.start() > prior.start:  # later mention wins
                        found[term.feature_id] = ExtractedObservation(
                            term.feature_id, m.start(), m.end(), message[m.start() : m.end()], presence
                        )
        observations = sorted(found.values(), key=lambda o: o.start)
        if not observations:
            stripped = message.strip()
            start = message.find(stripped) if stripped else 0
            observations = [ExtractedObservation(None, start, start + len(stripped), stripped, "uncertain")]
        return ExtractionResult(tuple(observations), self.version)


class UnavailableExtractor:
    """Stands in for an unconfigured or failing provider."""

    version = "unavailable"

    def extract(self, message: str, vocabulary: list[VocabularyTerm]) -> ExtractionResult:
        raise ExtractionError("extraction provider is not available")
