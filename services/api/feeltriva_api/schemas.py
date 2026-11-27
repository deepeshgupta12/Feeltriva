"""Pydantic transport models mirroring specs/openapi.json (checked by tests/contract)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PresenceT = Literal["present", "absent", "uncertain", "not_asked"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Demographics(_Strict):
    age_years: int | None = Field(default=None, ge=0, le=130)
    gender_identity: str | None = Field(default=None, max_length=100)
    clinically_relevant_context: dict[str, Any] | None = None


class SessionCreate(_Strict):
    consent_version: str = Field(min_length=1)
    # A separate choice from the agreement to use the service; false unless the person makes it (M3.16).
    training_consent: bool = False
    demographics: Demographics | None = None


# What the handoff asks to be known about a symptom beside onset, duration and severity (M3.12).
Attribute = Annotated[str | None, Field(default=None, min_length=1, max_length=200)]


class Observation(_Strict):
    feature_id: str
    presence: PresenceT
    value: Any = None
    onset: str | None = None
    duration: str | None = None
    severity: str | None = None
    location: Attribute
    pattern: Attribute
    triggers: Attribute
    relieving_factors: Attribute
    confirmed: bool
    supersedes: uuid.UUID | None = None


class ObservationSubmit(_Strict):
    observation_version: int = Field(ge=0)
    text: str | None = Field(default=None, min_length=1, max_length=10000)
    observations: list[Observation] | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def _one_of(self) -> ObservationSubmit:
        if (self.text is None) == (self.observations is None):
            raise ValueError("provide exactly one of 'text' or 'observations'")
        return self


class AnswerSubmit(_Strict):
    observation_version: int = Field(ge=0)
    question_id: str
    answer: Any


class AssessmentRequest(_Strict):
    observation_version: int = Field(ge=0)


class ObservationRecord(_Strict):
    feature_id: str | None
    presence: PresenceT
    value: Any = None
    onset: str | None = None
    duration: str | None = None
    severity: str | None = None
    location: str | None = None
    pattern: str | None = None
    triggers: str | None = None
    relieving_factors: str | None = None
    # In words, for a person to read (M3.12): the name of the item, and the stored answer as it was given.
    # `feature_id` and `value` stay what they are, internal values.
    display_name: str | None = None
    value_label: str | None = None
    confirmed: bool
    supersedes: uuid.UUID | None = None
    observation_id: uuid.UUID
    observation_version: int
    raw_phrase: str | None = None


class SessionOut(_Strict):
    session_id: uuid.UUID
    observation_version: int
    state: str
    expires_at: datetime
    observations: list[ObservationRecord]
    demographics: Demographics | None = None
    # What the person agreed to, and when (M3.16).
    consent_version: str | None = None
    consent_accepted_at: datetime | None = None
    training_consent: bool | None = None


class Candidate(_Strict):
    disease_id: str
    name: str
    supporting_observation_ids: list[uuid.UUID]
    conflicting_observation_ids: list[uuid.UUID]
    evidence_ids: list[str]
    explanation: str


class NextAction(_Strict):
    type: Literal["ask_question", "seek_care", "show_summary", "retry"]
    text: str
    question_id: str | None = None


class Versions(_Strict):
    knowledge: str | None
    rules: str | None
    model: str | None
    prompt: str | None


class Evidence(_Strict):
    evidence_id: str
    source_title: str
    source_url: str | None
    excerpt: str
    knowledge_release: str


class AssessmentOut(_Strict):
    assessment_id: uuid.UUID
    session_id: uuid.UUID
    observation_version: int
    status: Literal[
        "needs_clarification",
        "provisional",
        "urgent_handoff",
        "out_of_scope",
        "insufficient_information",
        "system_unavailable",
    ]
    urgency: Literal["not_assessed", "emergency", "urgent", "routine", "self_care_with_safety_net"]
    candidates: list[Candidate] = Field(max_length=3)
    unknowns: list[str]
    next_action: NextAction
    evidence_ids: list[str]
    versions: Versions
    evidence: list[Evidence]


class QuestionOut(_Strict):
    question_id: str
    wording: str
    answer_schema: dict[str, Any]
    observation_version: int


class SummaryOut(_Strict):
    session_id: uuid.UUID
    observation_version: int
    summary_text: str
    requires_user_review: Literal[True] = True


class DeletionReceipt(_Strict):
    session_id: uuid.UUID
    status: Literal["deletion_scheduled", "deleted"]
    receipt_id: str


class ErrorOut(_Strict):
    code: str
    message: str
    retryable: bool
    request_id: str


_REQUIRED_NULLABLE = {"knowledge", "rules", "model", "prompt", "source_url", "feature_id"}


def _prune(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _prune(v) for k, v in value.items() if v is not None or k in _REQUIRED_NULLABLE}
    if isinstance(value, list):
        return [_prune(v) for v in value]
    return value


def dump(model: BaseModel) -> dict[str, Any]:
    """JSON-ready dict. Optional fields that are unset are omitted (the contract does not allow
    null for them); required-but-nullable contract fields are kept as null."""
    return _prune(model.model_dump(mode="json"))
