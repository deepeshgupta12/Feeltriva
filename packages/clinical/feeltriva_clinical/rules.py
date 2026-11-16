"""Bounded declarative rule AST with three-valued (Kleene) logic.

Rules are data, never executable code. Unknown inputs stay unknown: a missing or
unasked feature can satisfy neither a positive nor a negative predicate.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

MAX_DEPTH = 8
MAX_NODES = 200

Tri = bool | None  # True, False or None (= unknown)

_COMPARATORS = {
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b,
    "eq": lambda a, b: a == b,
}
_FIELDS = {"demographics.age_years"}
_NODE_KEYS = {
    "and": {"op", "args"},
    "or": {"op", "args"},
    "not": {"op", "arg"},
    "present": {"op", "feature"},
    "absent": {"op", "feature"},
    "missing": {"op", "feature"},
    "compare": {"op", "field", "cmp", "value"},
}


class RuleValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Facts:
    """Inputs to rule evaluation.

    presence maps feature_id -> 'present' | 'absent' | 'uncertain' | 'not_asked'.
    A feature that is not in the mapping has never been observed.
    """

    presence: Mapping[str, str] = field(default_factory=dict)
    fields: Mapping[str, float | int | None] = field(default_factory=dict)


def validate_ast(node: Any, known_features: set[str]) -> None:
    count = 0

    def walk(n: Any, depth: int) -> None:
        nonlocal count
        count += 1
        if count > MAX_NODES:
            raise RuleValidationError(f"rule exceeds {MAX_NODES} nodes")
        if depth > MAX_DEPTH:
            raise RuleValidationError(f"rule exceeds depth {MAX_DEPTH}")
        if not isinstance(n, dict) or not isinstance(n.get("op"), str):
            raise RuleValidationError("node must be an object with a string 'op'")
        op = n["op"]
        if op not in _NODE_KEYS:
            raise RuleValidationError(f"unknown op {op!r}")
        if set(n) != _NODE_KEYS[op]:
            raise RuleValidationError(f"op {op!r} requires exactly keys {sorted(_NODE_KEYS[op])}")
        if op in ("and", "or"):
            if not isinstance(n["args"], list) or not n["args"]:
                raise RuleValidationError(f"{op!r} requires a non-empty args list")
            for child in n["args"]:
                walk(child, depth + 1)
        elif op == "not":
            walk(n["arg"], depth + 1)
        elif op in ("present", "absent", "missing"):
            if n["feature"] not in known_features:
                raise RuleValidationError(f"unknown feature reference {n['feature']!r}")
        elif op == "compare":
            if n["field"] not in _FIELDS:
                raise RuleValidationError(f"unknown field {n['field']!r}")
            if n["cmp"] not in _COMPARATORS:
                raise RuleValidationError(f"unknown comparator {n['cmp']!r}")
            if isinstance(n["value"], bool) or not isinstance(n["value"], int | float):
                raise RuleValidationError("compare value must be a number")

    walk(node, 1)


def evaluate(node: dict[str, Any], facts: Facts) -> Tri:
    op = node["op"]
    if op == "and":
        results = [evaluate(c, facts) for c in node["args"]]
        if any(r is False for r in results):
            return False
        return None if any(r is None for r in results) else True
    if op == "or":
        results = [evaluate(c, facts) for c in node["args"]]
        if any(r is True for r in results):
            return True
        return None if any(r is None for r in results) else False
    if op == "not":
        inner = evaluate(node["arg"], facts)
        return None if inner is None else not inner
    if op == "present":
        state = facts.presence.get(node["feature"])
        return True if state == "present" else False if state == "absent" else None
    if op == "absent":
        state = facts.presence.get(node["feature"])
        return True if state == "absent" else False if state == "present" else None
    if op == "missing":
        return facts.presence.get(node["feature"]) in (None, "not_asked")
    if op == "compare":
        value = facts.fields.get(node["field"])
        if value is None:
            return None
        return bool(_COMPARATORS[node["cmp"]](value, node["value"]))
    raise RuleValidationError(f"unknown op {op!r}")


def referenced_features(node: dict[str, Any]) -> list[str]:
    op = node["op"]
    if op in ("and", "or"):
        out: list[str] = []
        for c in node["args"]:
            out.extend(referenced_features(c))
        return out
    if op == "not":
        return referenced_features(node["arg"])
    if op in ("present", "absent", "missing"):
        return [node["feature"]]
    return []
