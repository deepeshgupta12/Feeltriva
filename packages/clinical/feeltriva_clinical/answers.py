"""Validation of follow-up answers against a question's answer_schema.

Returns the observation the answer implies. Pure functions; no clinical content.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ANSWER_TYPES = {"yes_no_unsure", "single_choice", "multiple_choice", "number", "duration", "free_text"}
DURATION_UNITS = ("hours", "days", "weeks", "months")
NOT_SURE = "not_sure"


class AnswerValidationError(ValueError):
    pass


@dataclass(frozen=True)
class AnswerOutcome:
    presence: str
    value: Any = None
    duration: str | None = None
    raw_phrase: str | None = None


def validate_answer_schema(schema: dict[str, Any]) -> None:
    kind = schema.get("type")
    if kind not in ANSWER_TYPES:
        raise AnswerValidationError(f"unknown answer type {kind!r}")
    if kind in ("single_choice", "multiple_choice"):
        options = schema.get("options")
        if not isinstance(options, list) or not options:
            raise AnswerValidationError("choice questions require options")
        values = [o.get("value") for o in options if isinstance(o, dict)]
        if len(values) != len(options) or len(set(values)) != len(values) or NOT_SURE in values:
            raise AnswerValidationError("options need unique values distinct from 'not_sure'")


def _number(raw: Any, schema: dict[str, Any]) -> float | int:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise AnswerValidationError("value must be a number")
    if "min" in schema and raw < schema["min"]:
        raise AnswerValidationError(f"value must be at least {schema['min']}")
    if "max" in schema and raw > schema["max"]:
        raise AnswerValidationError(f"value must be at most {schema['max']}")
    return raw


def interpret_answer(
    schema: dict[str, Any], answer: Any, option_presence: dict[str, str] | None = None
) -> AnswerOutcome:
    """Validate `answer` and map it to an observation outcome.

    `option_presence` is reviewer-authored mapping of option value -> presence for choice
    questions (e.g. an explicit "none of these" option meaning absent).
    """
    kind = schema["type"]
    allow_not_sure = bool(schema.get("allow_not_sure"))
    option_presence = option_presence or {}
    if kind == "yes_no_unsure":
        if answer == "yes":
            return AnswerOutcome("present")
        if answer == "no":
            return AnswerOutcome("absent")
        if answer == NOT_SURE:
            return AnswerOutcome("uncertain")
        raise AnswerValidationError("answer must be 'yes', 'no' or 'not_sure'")
    if kind == "single_choice":
        if answer == NOT_SURE:
            if not allow_not_sure:
                raise AnswerValidationError("'not_sure' is not allowed for this question")
            return AnswerOutcome("uncertain")
        values = {o["value"] for o in schema["options"]}
        if not isinstance(answer, str) or answer not in values:
            raise AnswerValidationError("answer must be one of the offered options")
        return AnswerOutcome(option_presence.get(answer, "present"), value=answer)
    if kind == "multiple_choice":
        values = {o["value"] for o in schema["options"]}
        if not isinstance(answer, list) or not answer or len(set(answer)) != len(answer):
            raise AnswerValidationError("answer must be a non-empty list of distinct options")
        if any(not isinstance(a, str) or a not in values for a in answer):
            raise AnswerValidationError("answer contains an option that was not offered")
        presences = {option_presence.get(a, "present") for a in answer}
        if len(presences) > 1:
            raise AnswerValidationError("selected options contradict each other")
        return AnswerOutcome(presences.pop(), value=list(answer))
    if kind == "number":
        if answer == NOT_SURE and allow_not_sure:
            return AnswerOutcome("uncertain")
        if not isinstance(answer, dict) or set(answer) - {"value", "unit"}:
            raise AnswerValidationError("answer must be an object with 'value' and optional 'unit'")
        value = _number(answer.get("value"), schema)
        unit = answer.get("unit")
        allowed = schema.get("units") or ([schema["unit"]] if schema.get("unit") else [])
        if allowed and unit not in allowed:
            raise AnswerValidationError(f"unit must be one of {allowed}")
        if not allowed and unit is not None:
            raise AnswerValidationError("this question does not take a unit")
        return AnswerOutcome("present", value={"value": value, "unit": unit})
    if kind == "duration":
        if answer == NOT_SURE and allow_not_sure:
            return AnswerOutcome("uncertain")
        if not isinstance(answer, dict) or set(answer) != {"value", "unit"}:
            raise AnswerValidationError("answer must be an object with 'value' and 'unit'")
        value = _number(answer["value"], {"min": 0, **schema})
        if answer["unit"] not in DURATION_UNITS:
            raise AnswerValidationError(f"unit must be one of {list(DURATION_UNITS)}")
        return AnswerOutcome(
            "present", value={"value": value, "unit": answer["unit"]}, duration=f"{value} {answer['unit']}"
        )
    if kind == "free_text":
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 2000:
            raise AnswerValidationError("answer must be non-empty text of at most 2000 characters")
        # Free text is not normalised into a finding: it stays uncertain until reviewed/confirmed.
        return AnswerOutcome("uncertain", raw_phrase=answer.strip())
    raise AnswerValidationError(f"unknown answer type {kind!r}")
