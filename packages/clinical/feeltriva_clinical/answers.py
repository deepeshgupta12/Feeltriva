"""Validation of follow-up answers against a question's answer_schema.

Returns the observation the answer implies. Pure functions; no clinical content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

ANSWER_TYPES = {"yes_no_unsure", "single_choice", "multiple_choice", "number", "duration", "date", "free_text"}
DURATION_UNITS = ("hours", "days", "weeks", "months")
NOT_SURE = "not_sure"
# A date question may bound its answer with `earliest` and `latest`: a calendar date, or the word "today".
TODAY = "today"
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# "Today" is the day of whoever answers. Their calendar can be a day ahead of or behind the service's own, so a
# bound given as "today" allows one day either way; a bound given as a date is exact.
_DAY = timedelta(days=1)


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
    if kind == "date":
        fixed = {}
        for key in ("earliest", "latest"):
            if key in schema and schema[key] != TODAY:
                fixed[key] = _calendar_date(schema[key], f"'{key}'")
        if len(fixed) == 2 and fixed["earliest"] > fixed["latest"]:
            raise AnswerValidationError("'earliest' must not be after 'latest'")


def _calendar_date(raw: Any, what: str) -> date:
    """A calendar date written YYYY-MM-DD, and one that exists."""
    if not isinstance(raw, str) or not _ISO_DATE.match(raw):
        raise AnswerValidationError(f"{what} must be a date written as YYYY-MM-DD")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise AnswerValidationError(f"{what} is not a date in the calendar") from exc


def _number(raw: Any, schema: dict[str, Any]) -> float | int:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise AnswerValidationError("value must be a number")
    if "min" in schema and raw < schema["min"]:
        raise AnswerValidationError(f"value must be at least {schema['min']}")
    if "max" in schema and raw > schema["max"]:
        raise AnswerValidationError(f"value must be at most {schema['max']}")
    return raw


def interpret_answer(
    schema: dict[str, Any],
    answer: Any,
    option_presence: dict[str, str] | None = None,
    *,
    today: date | None = None,
) -> AnswerOutcome:
    """Validate `answer` and map it to an observation outcome.

    `option_presence` is reviewer-authored mapping of option value -> presence for choice
    questions (e.g. an explicit "none of these" option meaning absent).

    "Not sure" is the one string `not_sure` for every type of question (BUG-010): always for yes / no, and
    for the other types when the question allows it. `today` is the day a "today" bound of a date question is
    read against; the service's own day when not given.
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
        if answer == NOT_SURE:
            if not allow_not_sure:
                raise AnswerValidationError("'not_sure' is not allowed for this question")
            return AnswerOutcome("uncertain")
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
    if kind == "date":
        if answer == NOT_SURE:
            if not allow_not_sure:
                raise AnswerValidationError("'not_sure' is not allowed for this question")
            return AnswerOutcome("uncertain")
        if not isinstance(answer, dict) or set(answer) != {"date"}:
            raise AnswerValidationError("answer must be an object with 'date' written as YYYY-MM-DD")
        day = _calendar_date(answer["date"], "the date")
        reference = today or datetime.now(UTC).date()
        earliest, latest = schema.get("earliest"), schema.get("latest")
        if earliest is not None:
            bound = reference - _DAY if earliest == TODAY else _calendar_date(earliest, "'earliest'")
            if day < bound:
                raise AnswerValidationError(
                    "the date must not be before today"
                    if earliest == TODAY
                    else f"the date must not be before {earliest}"
                )
        if latest is not None:
            bound = reference + _DAY if latest == TODAY else _calendar_date(latest, "'latest'")
            if day > bound:
                raise AnswerValidationError(
                    "the date must not be after today" if latest == TODAY else f"the date must not be after {latest}"
                )
        # The value says what it is: a date, not an option of a choice question and not free text.
        return AnswerOutcome("present", value={"date": day.isoformat()})
    if kind == "free_text":
        if answer == NOT_SURE and allow_not_sure:
            return AnswerOutcome("uncertain")
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 2000:
            raise AnswerValidationError("answer must be non-empty text of at most 2000 characters")
        # Free text is not normalised into a finding: it stays uncertain until reviewed/confirmed.
        return AnswerOutcome("uncertain", raw_phrase=answer.strip())
    raise AnswerValidationError(f"unknown answer type {kind!r}")


def answer_in_words(schema: dict[str, Any] | None, answer: Any) -> str | None:
    """A stored answer as a person reads it, or None when there is nothing that can be said in words (M3.14a).

    Written for the summary the service gives back. The internal value of an option is never returned: it is
    said in the option's own words, and left out when the question does not have it. A number keeps its unit,
    a length of time is "1 day" or "3 days", a date is written out. `schema` is the question's, or None when
    the value belongs to no question.
    """
    if answer is None:
        return None
    if answer == NOT_SURE:
        return "Not sure"
    schema = schema or {}
    kind = schema.get("type")
    labels = {
        option["value"]: option["label"]
        for option in schema.get("options") or []
        if isinstance(option, dict) and isinstance(option.get("value"), str) and isinstance(option.get("label"), str)
    }
    if isinstance(answer, str):
        if kind == "yes_no_unsure":
            return {"yes": "Yes", "no": "No"}.get(answer)
        if kind == "free_text":
            return answer
        return labels.get(answer)
    if isinstance(answer, list):
        said = [labels[item] for item in answer if isinstance(item, str) and item in labels]
        return ", ".join(said) or None
    if isinstance(answer, dict):
        if isinstance(answer.get("date"), str):
            try:
                day = _calendar_date(answer["date"], "the date")
            except AnswerValidationError:
                return None
            return f"{day.day} {day:%B %Y}"
        value, unit = answer.get("value"), answer.get("unit")
        if isinstance(value, int | float) and not isinstance(value, bool):
            if isinstance(unit, str) and unit:
                if unit in DURATION_UNITS and value == 1:
                    unit = unit[:-1]
                return f"{value} {unit}"
            return str(value)
    return None
