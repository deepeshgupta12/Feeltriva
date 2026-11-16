"""Application service for assessments. REST and MCP both call this class and nothing else:
ownership, consent, idempotency, observation versions, urgency/scope screening and response
shaping all live here so no transport can bypass them.

The implementation is split by responsibility:
`service_core` (shared machinery), `service_intake` (sessions, observations, answers,
questions) and `service_results` (assessment, summary, deletion).
"""

from __future__ import annotations

from .service_intake import IntakeOperations
from .service_results import ResultOperations


class AssessmentService(IntakeOperations, ResultOperations):
    """The single entry point used by every transport."""
