"""The routes of the review workspace as the service itself describes them (M3.12).

The assessment API has a written contract (`packages/contracts/openapi.json`). The review workspace
(`/internal/v1/review/…`) had none: its routes were added sub-step by sub-step and were listed nowhere. This
module writes their description, taken from the running application, to
`packages/contracts/openapi.internal.json`, and a test checks that the file is current, so a route cannot be
added, removed or change what it takes without the file saying so.

What it holds: every route with its method, its parameters and the body it takes. What it does not hold: the
shape of the answers, which the routes do not declare yet.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PATH = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "openapi.internal.json"
PREFIX = "/internal/"


def _refs(node: Any) -> set[str]:
    if isinstance(node, dict):
        found = {node["$ref"].rsplit("/", 1)[1]} if isinstance(node.get("$ref"), str) else set()
        return found.union(*(_refs(value) for value in node.values()))
    if isinstance(node, list):
        return set().union(*(_refs(value) for value in node))
    return set()


def internal_contract(app: Any) -> dict[str, Any]:
    """The description of the internal routes of this application, with the shapes they name."""
    full = app.openapi()
    paths = {path: item for path, item in sorted(full["paths"].items()) if path.startswith(PREFIX)}
    schemas = full.get("components", {}).get("schemas", {})
    needed: set[str] = set()
    todo = _refs(paths)
    while todo:
        name = todo.pop()
        if name not in needed and name in schemas:
            needed.add(name)
            todo |= _refs(schemas[name]) - needed
    return {
        "openapi": full["openapi"],
        "info": {
            "title": "Feeltriva review workspace API (internal)",
            "version": full["info"]["version"],
            "description": "For reviewers only. Written from the running service by `python -m feeltriva_api.contract`; "
            "do not edit by hand.",
        },
        "paths": paths,
        "components": {"schemas": {name: schemas[name] for name in sorted(needed)}},
    }


def render(contract: dict[str, Any]) -> str:
    return json.dumps(contract, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    from .main import app_factory

    contract = internal_contract(app_factory())
    PATH.write_text(render(contract), encoding="utf-8")
    print(f"{PATH.relative_to(PATH.parents[2])}: {sum(len(item) for item in contract['paths'].values())} operations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
