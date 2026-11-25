"""Names without a link in the review path, and what confirming a proposed term makes (M2.4b).

The look-ups store a link only for an exact name or for the one identifier a vocabulary marks
equivalent. Everything else is a row of `link_proposals`: a close ICD-11 search result, a term near
our name in HPO or MONDO, one of several identifiers MONDO marks equivalent, or only the reason a
name has no link. Reviewers see these rows and decide them through the same decision endpoint as
every other review target.

What a decision does, in the reviewer's own transaction and under the reviewer's name:

- Confirming (approving) a row that names a term makes the link: one row of `terminology_links`
  with the row's code, title and address, approved. The rules for approving a link apply to it
  unchanged (the general term is the default; a link is not approved while the MONDO link it was
  taken through is rejected), so a confirmation can be refused, with the reason. If the link is
  there already by another route, it is approved, not made twice.
- Rejecting a row makes no link. If the row was confirmed before, the link made from it is rejected
  with it; setting the row back to pending sets that link back to pending. A link that came by
  another route is left as it is.
- A row without a term, and a row whose term cannot be linked (an obsolete term), records why the
  name has no link. A note can be written on it; it is not confirmed or rejected.

Until a reviewer confirms a row, nothing of it is a link (decision E56). Codes are internal: these
rows are for reviewers only (decision E63), and a refusal names titles and our own IDs, never a code.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import case, func, or_, select

from .auth import Principal
from .db import Database
from .errors import ApiError
from .models import AuditEvent, Disease, Feature, LinkProposal, ReviewNote, TerminologyLink
from .review import _GUARDS, _TARGETS, _link_guard, _page

TARGET = "link_proposal"
METHOD = "reviewer_confirmed"  # how a link made from a confirmed proposal was found
# The kinds of row, in the order a reviewer is shown them, with what each means in plain words. The ingestion
# pipeline writes these names (`feeltriva_ingestion.proposals`); a test keeps the two lists the same.
KINDS: dict[str, str] = {
    "abbreviation_only": "Our name matches only an abbreviation of the term",
    "several_terms_carry_the_name": "Several terms carry our name",
    "several_identifiers_marked_equivalent": "The vocabulary lists several codes as equivalent",
    "close_search_result": "Close search result, no exact name",
    "looser_synonym": "Our name matches only a looser synonym of the term",
    "nearest_by_shared_words": "Nearest term by shared words",
    "plain_word_not_the_abbreviation": "An ordinary word, not the abbreviation; nearest terms",
    "weak_search_result": "Weak search result, probably not the same",
    "term_not_linkable": "The only term with our name cannot be linked",
    "no_term_near": "No term near our name",
    "no_search_result": "The search found nothing for our name",
    "question_sentence_not_looked_up": "A question sentence, not looked up",
}
CONFIRMABLE = frozenset(
    {
        "abbreviation_only",
        "several_terms_carry_the_name",
        "several_identifiers_marked_equivalent",
        "close_search_result",
        "looser_synonym",
        "nearest_by_shared_words",
        "plain_word_not_the_abbreviation",  # the terms listed are the nearest ones; the abbreviation is ruled out
        "weak_search_result",  # the best the search gave, with a low score: a reviewer may still find it right
    }
)

_TARGETS[TARGET] = (LinkProposal, "proposal_id")


def _can_be_confirmed(proposal: LinkProposal) -> bool:
    return proposal.code is not None and proposal.basis in CONFIRMABLE


def list_link_proposals(
    db: Database,
    principal: Principal,
    *,
    status: str | None = None,
    system: str | None = None,
    basis: str | None = None,
    subject_type: str | None = None,
    decidable: bool | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """The names without a link and the terms proposed for them, for reviewers only.

    The rows a reviewer can confirm come first, by kind; within a kind by our name. `kinds` counts the whole
    table by kind, whatever the filters, so a screen can say how much there is to do."""
    principal.require_role("reviewer")
    limit, offset = _page(limit, offset)
    name = func.coalesce(Disease.preferred_name, Feature.preferred_name)
    confirmable = LinkProposal.code.is_not(None) & LinkProposal.basis.in_(CONFIRMABLE)
    stmt = (
        select(LinkProposal, name, TerminologyLink.status)
        .outerjoin(Disease, Disease.disease_id == LinkProposal.disease_id)
        .outerjoin(Feature, Feature.feature_id == LinkProposal.feature_id)
        .outerjoin(TerminologyLink, TerminologyLink.link_id == LinkProposal.link_id)
    )
    if status:
        stmt = stmt.where(LinkProposal.status == status)
    if system:
        stmt = stmt.where(LinkProposal.system == system)
    if basis:
        stmt = stmt.where(LinkProposal.basis == basis)
    if subject_type == "disease":
        stmt = stmt.where(LinkProposal.disease_id.is_not(None))
    elif subject_type == "feature":
        stmt = stmt.where(LinkProposal.feature_id.is_not(None))
    if decidable is True:
        stmt = stmt.where(confirmable)
    elif decidable is False:
        stmt = stmt.where(~confirmable)
    if q:
        pattern = q.lower()
        stmt = stmt.where(
            or_(
                func.lower(name).contains(pattern),
                func.lower(func.coalesce(LinkProposal.title, "")).contains(pattern),
                func.lower(func.coalesce(LinkProposal.code, "")).contains(pattern),
            )
        )
    rank = case({kind: number for number, kind in enumerate(KINDS)}, value=LinkProposal.basis, else_=len(KINDS))
    with db.transaction(principal.subject, role="reviewer") as tx:
        total = tx.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
        rows = tx.execute(
            stmt.order_by(rank, name, LinkProposal.system, LinkProposal.title, LinkProposal.proposal_id)
            .limit(limit)
            .offset(offset)
        ).all()
        counted = tx.execute(
            select(
                LinkProposal.basis,
                func.count(),
                func.sum(case((LinkProposal.status == "pending", 1), else_=0)),
                func.sum(case((LinkProposal.code.is_not(None), 1), else_=0)),
            ).group_by(LinkProposal.basis)
        ).all()
        by_kind = {
            basis_: (int(rows_), int(pending or 0), int(with_term or 0))
            for basis_, rows_, pending, with_term in counted
        }
        return {
            "label": "Names without a link to an outside vocabulary, and the terms proposed for them - internal, not "
            "shown to users; nothing here is a link until a reviewer confirms it",
            "total": total,
            "kinds": [
                {
                    "basis": kind,
                    "meaning": meaning,
                    "can_be_confirmed": kind in CONFIRMABLE,
                    "rows": by_kind.get(kind, (0, 0, 0))[0],
                    "pending": by_kind.get(kind, (0, 0, 0))[1],
                    "naming_a_term": by_kind.get(kind, (0, 0, 0))[2],
                }
                for kind, meaning in KINDS.items()
            ],
            "items": [
                {
                    "proposal_id": proposal.proposal_id,
                    "subject": {
                        "type": "disease" if proposal.disease_id else "feature",
                        "id": proposal.disease_id or proposal.feature_id,
                        "term": our_name,
                    },
                    "system": proposal.system,
                    "system_version": proposal.system_version,
                    "basis": proposal.basis,
                    "meaning": KINDS.get(proposal.basis, proposal.basis),
                    "reason": proposal.reason,
                    "term": (
                        {"code": proposal.code, "title": proposal.title, "uri": proposal.uri}
                        if proposal.code is not None
                        else None
                    ),
                    "can_be_confirmed": _can_be_confirmed(proposal),
                    "detail": proposal.detail or {},
                    "review_status": proposal.status,
                    "reviewer": proposal.reviewer,
                    # The link this row makes when confirmed, once it exists (made from this row or by another route).
                    "link": (
                        {"link_id": proposal.link_id, "review_status": link_status} if link_status is not None else None
                    ),
                }
                for proposal, our_name, link_status in rows
            ],
        }


def _decide_link(tx: Any, principal: Principal, link: TerminologyLink, status: str, proposal: LinkProposal) -> None:
    """Set the link a proposal makes to the status the decision on the proposal entails, with its own record."""
    _link_guard(tx, link, status, principal)  # the rules of every decision on a link; may refuse
    previous = link.status
    link.status, link.reviewer = status, principal.subject
    said = {
        "approved": "Confirmed by a reviewer from the proposal",
        "rejected": "Rejected with the proposal it was made from,",
        "pending": "Pending again with the proposal it was made from,",
    }[status]
    tx.add(
        ReviewNote(
            note_id=uuid.uuid4(),
            target_type="terminology_link",
            target_id=link.link_id,
            reviewer=principal.subject,
            note=f"{said} {proposal.proposal_id}: {proposal.reason}",
            status_change=status,
        )
    )
    tx.add(
        AuditEvent(
            event_id=uuid.uuid4(),
            actor_subject=principal.subject,
            event_type="review_recorded",
            redacted_metadata={
                "target_type": "terminology_link",
                "target_id": link.link_id,
                "from": previous,
                "to": status,
                "follows_the_decision_on_proposal": proposal.proposal_id,
            },
        )
    )


def _proposal_guard(tx: Any, proposal: LinkProposal, status: str, principal: Principal) -> None:
    if not _can_be_confirmed(proposal):
        raise ApiError(
            409,
            "nothing_to_confirm",
            "This row records why the name has no link; it names no term that could be linked, so there is nothing "
            "to confirm or reject. A note can be written on it.",
        )
    if status == "retired":
        raise ApiError(409, "proposal_not_retired", "A proposed term is confirmed or rejected; it is not retired.")
    link = tx.get(TerminologyLink, proposal.link_id)
    if status == "approved":
        if link is None:
            link = TerminologyLink(
                link_id=proposal.link_id,
                disease_id=proposal.disease_id,
                feature_id=proposal.feature_id,
                system=proposal.system,
                system_version=proposal.system_version,
                code=proposal.code,
                title=proposal.title,
                uri=proposal.uri,
                match_method=METHOD,
                detail={
                    **(proposal.detail or {}),
                    "proposal_id": proposal.proposal_id,
                    "basis": proposal.basis,
                    "reason": proposal.reason,
                },
                status="pending",
            )
            tx.add(link)
            tx.flush()
        if link.status != "approved":
            _decide_link(tx, principal, link, "approved", proposal)
    elif (
        link is not None
        and link.match_method == METHOD
        and (link.detail or {}).get("proposal_id") == proposal.proposal_id
        and link.status != status
    ):
        _decide_link(tx, principal, link, status, proposal)  # only the link this very row made follows it
    proposal.reviewer = principal.subject


_GUARDS[TARGET] = _proposal_guard
