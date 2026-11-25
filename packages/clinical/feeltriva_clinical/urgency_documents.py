"""The draft urgency rule set written out for people (M2.10a): a review document and a final text.

Both are generated from the draft file, so neither can say something the rules do not:

- the **review document** holds everything a reviewer needs to judge a rule: when it fires, the
  text shown, why it has its level, a case that fires and one that does not, and the published
  basis quoted word for word;
- the **final text** holds only what would be published: when each rule fires and what the person
  is shown, with the record in which the owner's approval is written down.

The documents are generated from the rule file and do not know what has been decided: decisions
are recorded in the system (M2.5a) for the file with a given fingerprint. Nothing here is shown
to a person.

This module is pure: it reads no file and no database.
"""

from __future__ import annotations

from typing import Any

from .urgency_draft import DraftRule, UrgencyDraft

REVIEW_FILE = "urgency_rules_draft.md"
FINAL_FILE = "urgency_rules_final.md"
_LEVELS = {
    "emergency": "Emergency",
    "urgent": "Urgent",
}
_MEANING = {
    "emergency": "The published advice is an ambulance or an emergency department now.",
    "urgent": "The published advice is help the same day, with an ambulance if named signs appear.",
}


def _names(draft: UrgencyDraft) -> dict[str, str]:
    return {feature.feature_id: feature.question or feature.name for feature in draft.features}


def _ordered(draft: UrgencyDraft) -> list[DraftRule]:
    return sorted(draft.rules, key=lambda rule: rule.priority)


def _quoted(ids: list[str], names: dict[str, str]) -> str:
    return "; ".join(f"“{names[feature]}”" for feature in ids)


def _when(node: dict[str, Any], names: dict[str, str], depth: int = 0) -> list[str]:
    """A condition as a list a reader can follow, one line per choice."""
    pad, op = "  " * depth, node["op"]
    if op == "present":
        return [f"{pad}- “{names[node['feature']]}”"]
    if op in ("absent", "missing"):
        word = "is known to be absent" if op == "absent" else "has not been asked about"
        return [f"{pad}- “{names[node['feature']]}” {word}"]
    if op == "not":
        return [f"{pad}- **not:**", *_when(node["arg"], names, depth + 1)]
    if op == "compare":
        return [f"{pad}- {node['field']} {node['cmp']} {node['value']}"]
    children = node["args"]
    if op == "or" and all(child["op"] == "present" for child in children):
        return [f"{pad}- any one of: " + _quoted([child["feature"] for child in children], names)]
    head = "any one of these is enough:" if op == "or" else "all of these together:"
    lines = [f"{pad}- **{head}**"]
    for child in children:
        lines += _when(child, names, depth + 1)
    return lines


def _banner(draft: UrgencyDraft) -> list[str]:
    return [
        "> **Not shown to anyone.** These rules reach a person only from a published release with clinical mode "
        "switched on. Neither exists yet.",
        f"> {draft.label}",
        "> Decisions on the rules are recorded in the system, with the name of who decided and the time, not in this "
        "document. The history at the end says what the owner decided.",
    ]


def _numbers(draft: UrgencyDraft) -> list[str]:
    sources = {source.evidence_id: source for source in draft.sources}
    lines = [
        "| Number | What it is | Quoted from | Confirmed by the owner |",
        "|---|---|---|---|",
    ]
    for entry in draft.numbers:
        quoted = "; ".join(f"[{sources[i].publisher}]({sources[i].source_url})" for i in entry.evidence_ids)
        lines.append(f"| **{entry.number}** | {entry.what} | {quoted} | {entry.confirmed_by_owner or 'not yet'} |")
    return lines


def _not_covered(draft: UrgencyDraft) -> list[str]:
    return [
        "| Published warning sign | Why there is no rule |",
        "|---|---|",
        *[f"| {item.sign} | {item.why} |" for item in draft.not_covered],
    ]


def _behaviour() -> list[str]:
    return [
        "- The rules are checked on every new or corrected answer, before any possible explanation is looked for.",
        "- A rule fires only when what has been recorded makes its condition true. A symptom nobody has asked "
        "about is unknown: it counts neither as present nor as absent.",
        "- Emergency rules are checked before urgent ones. The first rule that fires decides the text shown.",
        "- When a rule fires, the assessment stops asking routine questions and shows the rule's text first.",
        "- No rule uses a number as a threshold. Each asks only whether named symptoms are present.",
    ]


def review_document(draft: UrgencyDraft) -> str:
    """Everything a reviewer needs to judge the draft. Generated: change the draft file, not this text."""
    names = _names(draft)
    sources = {source.evidence_id: source for source in draft.sources}
    rules = _ordered(draft)
    number_of = {rule.rule_id: number for number, rule in enumerate(rules, 1)}
    emergency = sum(1 for rule in rules if rule.action.urgency == "emergency")
    lines = [
        "# Urgency rules: review document",
        "",
        *_banner(draft),
        "",
        f"Rule set `{draft.version}` for {draft.jurisdiction}, written {draft.written}. This document is generated from "
        "`packages/clinical/feeltriva_clinical/drafts/urgency_draft.json`: change the file, not this text. The "
        f"finished text for approval, without the working notes, is in [{FINAL_FILE}]({FINAL_FILE}).",
        "",
        "## 1. At a glance",
        "",
        f"{len(rules)} rules: {emergency} emergency and {len(rules) - emergency} urgent, over {len(draft.features)} "
        f"features of the vocabulary, resting on {len(draft.sources)} published pages.",
        "",
        "| No. | Rule | Level |",
        "|---:|---|---|",
        *[
            f"| {number_of[rule.rule_id]} | [{rule.title}](#rule-{number_of[rule.rule_id]}) | "
            f"{_LEVELS[rule.action.urgency or '']} |"
            for rule in rules
        ],
        "",
        "## 2. How the rules behave",
        "",
        *_behaviour(),
        "- The service does not load these rules today. It loads only the synthetic sample release.",
        "",
        "## 3. The two levels",
        "",
        "| Level | Meaning | Rules |",
        "|---|---|---:|",
        f"| Emergency | {_MEANING['emergency']} | {emergency} |",
        f"| Urgent | {_MEANING['urgent']} | {len(rules) - emergency} |",
        "",
        "## 4. Telephone numbers named in the texts",
        "",
        *_numbers(draft),
        "",
        "No other number appears in any text shown. A check refuses a draft whose texts name a number not listed here.",
        "",
        "## 5. Still open",
        "",
        *[f"{number}. {point}" for number, point in enumerate(draft.open_points, 1)],
        "",
        "## 6. Weaknesses that remain whatever is decided",
        "",
        *[f"- {limit}" for limit in draft.limits],
        "",
        "## 7. Published warning signs the rules do not cover",
        "",
        *_not_covered(draft),
        "",
        "## 8. The rules",
    ]
    for rule in rules:
        number = number_of[rule.rule_id]
        fires = next(case for case in rule.tests if case.fires)
        quiet = next(case for case in rule.tests if not case.fires)
        lines += [
            "",
            f'<a id="rule-{number}"></a>',
            f"### Rule {number}. {rule.title}",
            "",
            "| Level | Identifier | Checked in position |",
            "|---|---|---:|",
            f"| **{_LEVELS[rule.action.urgency or '']}** | `{rule.rule_id}` | {number} of {len(rules)} |",
            "",
            "**Fires when**",
            "",
            *_when(rule.condition_ast, names),
            "",
            "**The person is shown**",
            "",
            f"> {rule.action.text}",
            "",
            f"**Why this level.** {rule.why_this_level}",
            "",
            "**Checked with two cases**",
            "",
            f"- Fires: recorded as present {_quoted(fires.present, names)}.",
            f"- Does not fire: recorded as present {_quoted(quiet.present, names)}"
            + (f"; recorded as absent {_quoted(quiet.absent, names)}." if quiet.absent else "."),
            "",
            "**Basis, quoted word for word**",
            "",
        ]
        for evidence_id in rule.evidence_ids:
            source = sources[evidence_id]
            reviewed = f", page last reviewed {source.page_reviewed}" if source.page_reviewed else ""
            lines.append(f"- {source.publisher}, [{source.source_title}]({source.source_url}){reviewed}:")
            lines += [f"  - “{quote}”" for quote in source.quotes]
    used: dict[str, list[int]] = {}
    for rule in rules:
        for feature in dict.fromkeys(_features_of(rule.condition_ast)):
            used.setdefault(feature, []).append(number_of[rule.rule_id])
    lines += [
        "",
        "## 9. Sources and licences",
        "",
        "| Source | Used by rules | Licence and attribution |",
        "|---|---|---|",
        *[
            f"| {source.publisher}: [{source.source_title}]({source.source_url}) | "
            f"{', '.join(str(number_of[rule.rule_id]) for rule in rules if source.evidence_id in rule.evidence_ids)} | "
            f"{source.licence} |"
            for source in draft.sources
        ],
        "",
        "Information from the NHS website is licensed under the "
        "[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). "
        "The rules and the texts shown are this project's own wording and are not NHS content.",
        "",
        "## 10. Features the rules use",
        "",
        "A feature is a symptom or an answer in the vocabulary. Where the feature is a question of a source, the "
        "question is shown. Features of different sources that mean the same thing are listed separately, because "
        "no synonym has been approved yet.",
        "",
        "| Feature | Identifier | Used by rules |",
        "|---|---|---|",
        *[
            f"| {feature.question or feature.name} | `{feature.feature_id}` | "
            f"{', '.join(str(number) for number in used[feature.feature_id])} |"
            for feature in draft.features
        ],
        "",
        "## 11. History",
        "",
        "| Date | Change |",
        "|---|---|",
        *[f"| {entry.date} | {entry.change} |" for entry in draft.history],
        "",
    ]
    return "\n".join(lines)


def _features_of(node: dict[str, Any]) -> list[str]:
    if "feature" in node:
        return [node["feature"]]
    children = node.get("args") or ([node["arg"]] if "arg" in node else [])
    return [feature for child in children for feature in _features_of(child)]


def final_document(draft: UrgencyDraft, digest: str) -> str:
    """The finished text of the rule set, ready to be approved: what fires when, and what the person is shown.

    `digest` is the SHA-256 of the draft file, so an approval names exactly the text it was given for."""
    names = _names(draft)
    rules = _ordered(draft)
    lines = [
        "# Urgency rules: final text",
        "",
        *_banner(draft),
        "> **An approval is for this exact text**, named by the fingerprint at the end.",
        "",
        f"Rule set `{draft.version}` for {draft.jurisdiction}. This document is generated from the rule file; the "
        f"reasons, the published basis of every rule and the cases it was checked with are in "
        f"[{REVIEW_FILE}]({REVIEW_FILE}).",
        "",
        "## What this is",
        "",
        f"The complete text of the {len(rules)} urgency rules as they would be published. For each rule it says when "
        "the rule fires and the exact words the person is shown. Nothing else in these rules reaches a person.",
        "",
        "The warning signs behind the rules are taken from pages of the NHS website (England), licensed under the "
        "[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). "
        "The texts shown are this project's own wording and are not NHS content. Every source is listed in the "
        "review document.",
        "",
        "## Still open",
        "",
        *[f"- {point}" for point in draft.open_points],
        "",
        "## How the rules are applied",
        "",
        *_behaviour(),
        "",
        "## Telephone numbers",
        "",
        *_numbers(draft),
    ]
    for level, heading in (("emergency", "Emergency rules (checked first)"), ("urgent", "Urgent rules")):
        lines += ["", f"## {heading}", "", _MEANING[level]]
        for number, rule in enumerate(rules, 1):
            if rule.action.urgency != level:
                continue
            lines += [
                "",
                f"### {number}. {rule.title}",
                "",
                "**When**",
                "",
                *_when(rule.condition_ast, names),
                "",
                "**The person is shown**",
                "",
                f"> {rule.action.text}",
            ]
    lines += [
        "",
        "## What these rules do not cover",
        "",
        *_not_covered(draft),
        "",
        "## What stays true after approval",
        "",
        *[f"- {limit}" for limit in draft.limits],
        "",
        "## Approval",
        "",
        "An approval is given for the rule file with the fingerprint below, and is recorded in the system through "
        "the review path with the name of who approved and the time. If the file changes, the fingerprint changes "
        "and a new approval is needed.",
        "",
        "| | |",
        "|---|---|",
        f"| Rule set | `{draft.version}` |",
        f"| Fingerprint of the rule file (SHA-256) | `{digest}` |",
        "| Where the approval is recorded | The review path of the service: `GET /internal/v1/review/rules` |",
        "",
        "## History",
        "",
        "| Date | Change |",
        "|---|---|",
        *[f"| {entry.date} | {entry.change} |" for entry in draft.history],
        "",
    ]
    return "\n".join(lines)


# -- the rules in words, for the review screen (M2.4c) ------------------------------------------------
def _line(line: str) -> dict[str, Any]:
    """One line of a condition as `_when` lists it: how deep it stands, its words, and whether it heads a group."""
    text = line.lstrip(" ")
    words = text.removeprefix("- ")
    heads = words.startswith("**") and words.endswith("**")
    return {"depth": (len(line) - len(text)) // 2, "text": words.strip("*") if heads else words, "heads_a_group": heads}


def rules_in_words(draft: UrgencyDraft) -> dict[str, dict[str, Any]]:
    """Each rule of the draft in the words of the review document, by its identifier.

    The review screen shows these. They are written by the same functions as the document, and a test compares
    the two, so that what a reviewer reads on the screen is what the document says."""
    names = _names(draft)
    sources = {source.evidence_id: source for source in draft.sources}
    rules = _ordered(draft)
    words: dict[str, dict[str, Any]] = {}
    for number, rule in enumerate(rules, 1):
        fires = next(case for case in rule.tests if case.fires)
        quiet = next(case for case in rule.tests if not case.fires)
        level = rule.action.urgency or ""
        words[rule.rule_id] = {
            "number": number,
            "of": len(rules),
            "title": rule.title,
            "level": _LEVELS[level],
            "level_meaning": _MEANING[level],
            "fires_when": [_line(line) for line in _when(rule.condition_ast, names)],
            "shown": rule.action.text,
            "why_this_level": rule.why_this_level,
            "checked_with": {
                "fires": f"recorded as present {_quoted(fires.present, names)}",
                "does_not_fire": f"recorded as present {_quoted(quiet.present, names)}"
                + (f"; recorded as absent {_quoted(quiet.absent, names)}" if quiet.absent else ""),
            },
            "basis": [
                {
                    "publisher": source.publisher,
                    "title": source.source_title,
                    "url": source.source_url,
                    "page_reviewed": source.page_reviewed,
                    "quotes": list(source.quotes),
                }
                for source in (sources[evidence_id] for evidence_id in rule.evidence_ids)
            ],
        }
    return words
