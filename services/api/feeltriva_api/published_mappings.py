"""Features and diseases in the review path, and the published mapping release (M2.5c2).

A reviewer decides a feature and a disease through the same decision endpoint as every other
review target. A label that is merged into another is not decided: the kept label is, or the
merged one is split out first.

A mapping release is a snapshot of what is approved at the time it is published:

- the approved features, with their kind, value type and other names;
- the approved diseases, each with its synonyms (the labels merged into it and its former names);
- the redirects from each merged label to the label kept;
- the approved mappings of source labels and source columns in one mapping working set, where
  the disease or feature they point at is approved too;
- the sources those mappings come from, with their SHA-256.

Nothing that is pending, rejected or retired is in it: an unapproved feature, disease or mapping
cannot be published. An approved mapping whose disease or feature is not approved is held back
and counted. The release also records how much of the working set was still undecided.

A release holds no code of an outside vocabulary (decision E63): vocabulary links stay in their
own table, which only a reviewer can read. Publishing serves nothing; the serving bundle takes
its features from the current mapping release in a later sub-step.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from feeltriva_clinical import load_fixture_bundle
from sqlalchemy import func, select

from . import publishing
from .auth import Principal
from .db import Database
from .errors import ApiError
from .feature_merges import other_names
from .models import (
    Disease,
    DiseaseHistory,
    DiseaseMapping,
    Feature,
    FeatureMapping,
    MappingRelease,
    PublishedMapping,
    ReviewNote,
    Source,
)
from .review import _GUARDS, _TARGETS, REVIEW_STATES, _page

KIND = "mapping_release"
COUNTED = ("features", "diseases", "redirects", "disease_mappings", "feature_mappings", "sources")
# Notes on the state of review inside a mapping's stored details. In a published release they would
# say "pending" about a mapping that was approved, so they are left out of it.
_REVIEW_NOTES = ("audit_status",)

_TARGETS["feature"] = (Feature, "feature_id")
_TARGETS["disease"] = (Disease, "disease_id")


@lru_cache
def sample_items() -> frozenset[str]:
    """The invented items of the synthetic test rule set. They are stored beside the real items, because the
    service runs on them while clinical mode is off; they are samples and never part of the vocabulary (BUG-037)."""
    return frozenset(load_fixture_bundle().feature_ids())


def _disease_guard(tx: Any, disease: Disease, status: str, principal: Principal) -> None:
    if disease.redirected_to:
        raise ApiError(
            409,
            "disease_is_merged",
            f"This label is merged into {disease.redirected_to}. Decide that label, or split this one out first.",
        )


_GUARDS["disease"] = _disease_guard


def _feature_guard(tx: Any, feature: Feature, status: str, principal: Principal) -> None:
    if status == "approved" and feature.feature_id in sample_items():
        raise ApiError(
            409,
            "sample_item",
            "This is an invented sample of the test rule set, not an item of the vocabulary. It cannot be approved.",
        )
    if feature.redirected_to:
        raise ApiError(
            409,
            "feature_is_merged",
            f"This name is merged into {feature.redirected_to}. Decide that item, or take this name out first.",
        )


_GUARDS["feature"] = _feature_guard


def _decisions(tx: Any, target_type: str, ids: list[str]) -> dict[str, ReviewNote]:
    """The last recorded decision on each of these targets."""
    if not ids:
        return {}
    notes = tx.scalars(
        select(ReviewNote)
        .where(
            ReviewNote.target_type == target_type,
            ReviewNote.target_id.in_(ids),
            ReviewNote.status_change.is_not(None),
        )
        .order_by(ReviewNote.created_at)
    ).all()
    return {note.target_id: note for note in notes}


def _listed(
    db: Database,
    principal: Principal,
    model: Any,
    key: str,
    target_type: str,
    filters: list[Any],
    status: str | None,
    q: str | None,
    limit: int,
    offset: int,
    row: Any,
) -> dict[str, Any]:
    principal.require_role("reviewer")
    if status is not None and status not in REVIEW_STATES:
        raise ApiError(422, "invalid_review_status", "Unknown review status.")
    limit, offset = _page(limit, offset)
    if status:
        filters = [*filters, model.status == status]
    if q:
        filters = [*filters, func.lower(model.preferred_name).contains(q.lower())]
    with db.transaction(principal.subject, role="reviewer") as tx:
        tally = tx.execute(select(model.status, func.count()).group_by(model.status)).all()
        total = tx.scalar(select(func.count()).select_from(model).where(*filters)) or 0
        rows = tx.scalars(
            select(model)
            .where(*filters)
            .order_by(model.preferred_name, getattr(model, key))
            .limit(limit)
            .offset(offset)
        ).all()
        last = _decisions(tx, target_type, [getattr(item, key) for item in rows])
        items = []
        for item in rows:
            decision = last.get(getattr(item, key))
            items.append(
                {
                    **row(item),
                    "review_status": item.status,
                    "decided_by": decision.reviewer if decision else None,
                    "decision_note": decision.note if decision else None,
                }
            )
        return {
            "by_status": {state: count for state, count in tally},
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": items,
        }


def list_features(
    db: Database,
    principal: Principal,
    *,
    status: str | None = None,
    kind: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """The features with their review status and last decision, for reviewers only."""
    return _listed(
        db,
        principal,
        Feature,
        "feature_id",
        "feature",
        [Feature.kind == kind] if kind else [],
        status,
        q,
        limit,
        offset,
        lambda feature: {
            "feature_id": feature.feature_id,
            "name": feature.preferred_name,
            "kind": feature.kind,
            "value_type": feature.value_type,
            "unit": feature.unit,
            "other_names": feature.aliases or [],
            "merged_into": feature.redirected_to,
        },
    )


def list_diseases(
    db: Database,
    principal: Principal,
    *,
    status: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """The disease labels with their review status and last decision, for reviewers only."""
    return _listed(
        db,
        principal,
        Disease,
        "disease_id",
        "disease",
        [],
        status,
        q,
        limit,
        offset,
        lambda disease: {
            "disease_id": disease.disease_id,
            "name": disease.preferred_name,
            "definition": disease.definition,
            "merged_into": disease.redirected_to,
        },
    )


def _obstacles(content: dict[str, Any]) -> list[str]:
    """Everything that keeps this content from being published."""
    if not content["features"] and not content["diseases"]:
        return ["no feature and no disease is approved"]
    return []


def _content(tx: Any, working: MappingRelease) -> tuple[dict[str, Any], list[str]]:
    """What a release of this working set would hold now, and everything that keeps it from being published."""
    items = tx.scalars(select(Feature).order_by(Feature.feature_id)).all()
    features = [item for item in items if item.status == "approved" and not item.redirected_to]
    # A name merged into a kept item (M2.20) is not listed by itself: the kept item carries it as another name,
    # and a column or a fact that was given the merged name is read through the kept item.
    merged_items: dict[str, list[Feature]] = {}
    for item in items:
        if item.redirected_to:
            merged_items.setdefault(item.redirected_to, []).append(item)
    item_resolves = {item.feature_id: item.redirected_to or item.feature_id for item in items}
    labels = tx.scalars(select(Disease).order_by(Disease.disease_id)).all()
    kept = {label.disease_id: label for label in labels if label.status == "approved" and not label.redirected_to}
    merged: dict[str, list[Disease]] = {}
    for label in labels:
        if label.redirected_to in kept:
            merged.setdefault(label.redirected_to, []).append(label)
    former: dict[str, list[str]] = {}  # the names a kept label had before a reviewer gave it its standard name
    if kept:
        renames = tx.scalars(
            select(DiseaseHistory)
            .where(DiseaseHistory.action == "merge")
            .order_by(DiseaseHistory.created_at, DiseaseHistory.event_id)
        ).all()
        for event in renames:
            if event.other_id in kept and (event.detail or {}).get("renamed_to"):
                former.setdefault(event.other_id, []).append(event.detail["kept_name"])

    def synonyms(disease_id: str) -> list[str]:
        names = [*(label.preferred_name for label in merged.get(disease_id, [])), *former.get(disease_id, [])]
        return [name for name in dict.fromkeys(names) if name != kept[disease_id].preferred_name]

    resolves = {label.disease_id: label.redirected_to or label.disease_id for label in labels}
    approved_features = {feature.feature_id for feature in features}
    held = {"disease_mappings": 0, "feature_mappings": 0}
    disease_mappings, feature_mappings = [], []
    for mapping in tx.scalars(
        select(DiseaseMapping)
        .where(DiseaseMapping.release_id == working.release_id, DiseaseMapping.status == "approved")
        .order_by(DiseaseMapping.mapping_id)
    ).all():
        target = resolves.get(mapping.disease_id or "")
        if target not in kept:
            held["disease_mappings"] += 1
            continue
        disease_mappings.append(
            {
                "mapping_id": mapping.mapping_id,
                "source_id": mapping.source_id,
                "original_label": mapping.original_label,
                "original_id": mapping.original_id,
                "disease_id": mapping.disease_id,
                "resolves_to": target,
                "method": mapping.method,
            }
        )
    for column in tx.scalars(
        select(FeatureMapping)
        .where(FeatureMapping.release_id == working.release_id, FeatureMapping.status == "approved")
        .order_by(FeatureMapping.mapping_id)
    ).all():
        item_id = item_resolves.get(column.feature_id or "")
        if item_id not in approved_features:
            held["feature_mappings"] += 1
            continue
        details = {k: v for k, v in (column.transformation or {}).items() if k not in _REVIEW_NOTES}
        if isinstance(details.get("meaning"), dict):
            details["meaning"] = {k: v for k, v in details["meaning"].items() if k != "status"}
        feature_mappings.append(
            {
                "mapping_id": column.mapping_id,
                "source_id": column.source_id,
                "file_path": column.file_path,
                "column_index": column.column_index,
                "original_term": column.original_term,
                "feature_id": item_id,
                # Only when the column was given a name that is now merged into the item above.
                **({"named_feature_id": column.feature_id} if item_id != column.feature_id else {}),
                "zero_semantics": column.zero_semantics,
                "details": details,
            }
        )
    used = sorted({entry["source_id"] for entry in [*disease_mappings, *feature_mappings]})
    sources = (
        tx.scalars(select(Source).where(Source.source_id.in_(used)).order_by(Source.source_id)).all() if used else []
    )

    def pending(model: Any, *where: Any) -> int:
        return tx.scalar(select(func.count()).select_from(model).where(model.status == "pending", *where)) or 0

    content = {
        "mapping_release_id": working.release_id,
        "version": working.version,
        "features": [
            {
                "feature_id": feature.feature_id,
                "preferred_name": feature.preferred_name,
                "kind": feature.kind,
                "value_type": feature.value_type,
                "unit": feature.unit,
                "aliases": other_names(feature, merged_items.get(feature.feature_id, [])),
                **(
                    {"merged_items": [other.feature_id for other in merged_items[feature.feature_id]]}
                    if feature.feature_id in merged_items
                    else {}
                ),
            }
            for feature in features
        ],
        "diseases": [
            {
                "disease_id": disease_id,
                "preferred_name": label.preferred_name,
                "definition": label.definition,
                "synonyms": synonyms(disease_id),
                "merged_labels": [other.disease_id for other in merged.get(disease_id, [])],
            }
            for disease_id, label in kept.items()
        ],
        "redirects": {other.disease_id: disease_id for disease_id in kept for other in merged.get(disease_id, [])},
        "feature_redirects": {
            other.feature_id: feature.feature_id
            for feature in features
            for other in merged_items.get(feature.feature_id, [])
        },
        "disease_mappings": disease_mappings,
        "feature_mappings": feature_mappings,
        "sources": [
            {
                "source_id": source.source_id,
                "source_name": source.source_name,
                "version": source.version,
                "sha256": source.sha256,
            }
            for source in sources
        ],
        "unresolved": {
            "features": pending(Feature),
            "diseases": pending(Disease, Disease.redirected_to.is_(None)),
            "disease_mappings": pending(DiseaseMapping, DiseaseMapping.release_id == working.release_id),
            "feature_mappings": pending(FeatureMapping, FeatureMapping.release_id == working.release_id),
        },
        "held_back": held,
    }
    return content, _obstacles(content)


def _counts(content: dict[str, Any]) -> dict[str, Any]:
    return {
        **{part: len(content[part]) for part in COUNTED},
        "unresolved": content["unresolved"],
        "held_back": content["held_back"],
    }


def _summary(release: PublishedMapping) -> dict[str, Any]:
    return {**publishing.summary(release), "mapping_release_id": release.working_id, **_counts(release.content)}


def _working(tx: Any, mapping_release_id: str) -> MappingRelease:
    working = tx.get(MappingRelease, mapping_release_id)
    if working is None:
        raise ApiError(404, "mapping_release_not_found", "Mapping working set not found.")
    return working


def list_published(db: Database, principal: Principal) -> dict[str, Any]:
    principal.require_role("reviewer")
    with db.transaction(principal.subject, role="reviewer") as tx:
        return {
            "items": [
                {**publishing.summary(release), "mapping_release_id": release.working_id, **counts}
                for release, counts in publishing.listed(tx, PublishedMapping, _counts)
            ]
        }


def preview(db: Database, principal: Principal, mapping_release_id: str) -> dict[str, Any]:
    """What publishing this working set now would do. Changes nothing."""
    principal.require_role("reviewer")
    with db.transaction(principal.subject, role="reviewer") as tx:
        content, problems = _content(tx, _working(tx, mapping_release_id))
        return {
            "mapping_release_id": mapping_release_id,
            **publishing.outlook(tx, PublishedMapping, mapping_release_id, content, problems),
            **_counts(content),
        }


def publish(db: Database, principal: Principal, *, mapping_release_id: str, note: str) -> dict[str, Any]:
    principal.require_role("reviewer")
    publishing.check_note(note)
    with db.transaction(principal.subject, role="reviewer") as tx:
        content, problems = _content(tx, _working(tx, mapping_release_id))
        release = publishing.publish(
            tx,
            PublishedMapping,
            principal,
            kind=KIND,
            working_id=mapping_release_id,
            content=content,
            problems=problems,
            note=note,
        )
        return _summary(release)


def make_current(db: Database, principal: Principal, *, release_id: str, note: str) -> dict[str, Any]:
    """Make a published mapping release the current one (rollback). Nothing is removed."""
    principal.require_role("reviewer")
    publishing.check_note(note)
    with db.transaction(principal.subject, role="reviewer") as tx:
        release = publishing.make_current(tx, PublishedMapping, principal, kind=KIND, release_id=release_id, note=note)
        return _summary(release)
