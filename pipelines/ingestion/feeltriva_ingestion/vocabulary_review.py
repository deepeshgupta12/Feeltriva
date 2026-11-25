"""The names without an ICD-11 link, as rows for a reviewer (M2.4b, M2.4f).

`link-vocabularies` stores a link only for an entity that carries exactly our name. For every
other name it stores one row for a reviewer, built here from what the look-up found:

- a close result: the best result of the name search, with a score of 0.9 or more;
- a weak result: the best result, with a lower score;
- no result: the search found nothing for the name;
- a question sentence, which is never sent to the search.

The first two name a term a reviewer may confirm; the last two record only why there is no link.
A name that was not looked up, because its answer is not saved and WHO was not to be asked, gets
no row: nothing is known about it.

Kept apart from `vocabulary.py` so that module stays within the size the code graph can read.
"""

from __future__ import annotations

from typing import Any

from . import proposals
from .vocabulary import ICD, link_id

CLOSE_SCORE = 0.9  # from this score the best search result of a name is put before a reviewer (M2.11)


def close_results(items: list[dict[str, Any]], release: str, chapters: dict[str, str]) -> list[dict[str, Any]]:
    """One proposal for each name that no ICD-11 entity carries exactly and whose best search result is close.

    A result without an address is left out here and reported by `check`: code, title and address belong
    together wherever ICD-11 is stored."""
    rows = []
    for item in items:
        best = item["best"]
        if not item["sent"] or best is None or best["score"] < CLOSE_SCORE or not best["uri"]:
            continue
        if any(link["system"] == ICD for link in item["links"]):
            continue  # an entity carries the name exactly: that is the link
        rows.append(
            proposals.row(
                item,
                ICD,
                release,
                proposals.CLOSE_RESULT,
                "no ICD-11 entity carries exactly this name; this is the best result of the name search",
                {"code": best["code"], "title": best["title"], "uri": best["uri"]},
                link_id(item["id"], ICD, release, best["code"]),
                query=item["sent"],
                score=best["score"],
                chapter=best["chapter"],
                chapter_title=chapters.get(best["chapter"], ""),
                residual=best["residual"],
            )
        )
    return rows


def other_results(items: list[dict[str, Any]], release: str, chapters: dict[str, str]) -> list[dict[str, Any]]:
    """One row for each name without an ICD-11 link that `close_results` does not cover.

    A best result below the close score is a weak result: it names a term a reviewer may still confirm. A
    name the search found nothing for, and a question sentence that was not sent, get a row without a term
    that records why. A name that was not looked up for want of a saved answer gets no row: nothing is known
    about it."""
    rows = []
    for item in items:
        if item["not_asked"] or any(link["system"] == ICD for link in item["links"]):
            continue
        best = item["best"]
        if not item["sent"]:
            rows.append(
                proposals.row(
                    item,
                    ICD,
                    release,
                    proposals.SENTENCE,
                    "a question sentence is not a name; it is not sent to the name search",
                    None,
                    None,
                )
            )
        elif best is None:
            rows.append(
                proposals.row(
                    item,
                    ICD,
                    release,
                    proposals.NO_RESULT,
                    "the ICD-11 name search gave no result for this name",
                    None,
                    None,
                    query=item["sent"],
                )
            )
        elif best["score"] < CLOSE_SCORE and best["uri"]:
            rows.append(
                proposals.row(
                    item,
                    ICD,
                    release,
                    proposals.WEAK_RESULT,
                    "no ICD-11 entity carries this name; the best result of the name search is not close",
                    {"code": best["code"], "title": best["title"], "uri": best["uri"]},
                    link_id(item["id"], ICD, release, best["code"]),
                    query=item["sent"],
                    score=best["score"],
                    chapter=best["chapter"],
                    chapter_title=chapters.get(best["chapter"], ""),
                    residual=best["residual"],
                )
            )
    return rows
