"""The consent a person gives before a session starts (M3.16, owner decision E32).

The text is a file with a version. A session can be started only with the current version, so that what a person
agreed to is known exactly: the session keeps the version, and the time it was started is the time of the
agreement. Agreeing to the conversation being used to improve the product is a separate choice, kept on its
own and off unless the person makes it (the handoff's rule; whether it is to be required is the owner's open
decision D-L2).

Taking the agreement back is deleting the conversation, which the service already does on request.

The wording in the file is a draft for the owner's review. It is not legal advice, and no lawyer has read it.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .errors import ApiError

PATH = Path(__file__).parent / "texts" / "consent_in_en_draft.json"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Section(_Strict):
    heading: str = Field(min_length=1)
    paragraphs: list[str] = Field(min_length=1)


class Training(_Strict):
    label: str = Field(min_length=1)
    explanation: str = Field(min_length=1)


class ConsentText(_Strict):
    consent_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: Literal["draft", "approved"]
    note: str = ""
    language: str
    region: str
    title: str = Field(min_length=1)
    sections: list[Section] = Field(min_length=1)
    acknowledgement: str = Field(min_length=1)
    training: Training

    def shown(self) -> dict[str, object]:
        """What a person is shown: the text, without the notes of those who wrote it."""
        return self.model_dump(exclude={"note"})


def load(path: Path = PATH) -> ConsentText:
    return ConsentText.model_validate(json.loads(path.read_text(encoding="utf-8")))


@lru_cache
def current() -> ConsentText:
    return load()


def require_current(version: str) -> None:
    """Refuse an agreement to any text but the current one."""
    if version != current().version:
        raise ApiError(
            409,
            "consent_version_not_current",
            "The terms shown were not the current ones. Read the current terms and agree to them to start.",
        )
