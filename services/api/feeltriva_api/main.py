"""HTTP transport. Deliberately no `from __future__ import annotations`: FastAPI must resolve the
request-scoped dependency aliases (Who, Key) defined inside create_app at definition time."""

import logging
import uuid
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import (
    disease_merges,
    published_knowledge,
    published_mappings,
    releases,
    response_text_sets,
    review_bulk,
    review_claims,
    review_proposals,
    serving_bundle,
)
from . import schemas as sc
from .auth import Principal
from .container import Container, build_container
from .errors import ApiError
from .review import list_notes, list_terminology_links
from .review_rules import list_rules
from .service import AssessmentService
from .settings import Settings, get_settings

log = logging.getLogger("feeltriva.api")


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_type: str
    target_id: str
    note: str = Field(min_length=1, max_length=4000)
    status: str | None = None


class DiseaseMerge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_disease_id: str
    target_disease_id: str
    note: str = Field(min_length=1, max_length=4000)
    kept_name: str | None = None


class DiseaseSplit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disease_id: str
    note: str = Field(min_length=1, max_length=4000)


class ReleasePublish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bundle_id: str
    note: str = Field(min_length=1, max_length=4000)


class ReleaseSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    release_id: str
    note: str = Field(min_length=1, max_length=4000)


def _error(request: Request, status: int, code: str, message: str, retryable: bool) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "") or str(uuid.uuid4())
    body = sc.ErrorOut(code=code, message=message, retryable=retryable, request_id=request_id)
    return JSONResponse(body.model_dump(), status_code=status, headers={"X-Request-ID": request_id})


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    container = container or build_container(settings)
    app = FastAPI(
        title="Feeltriva assessment API",
        version="0.1.0",
        docs_url="/docs" if settings.is_local else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.is_local else None,
    )
    app.state.container = container
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
            expose_headers=["X-Request-ID"],
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Response:
        request.state.request_id = str(uuid.uuid4())
        response: Response = await call_next(request)
        response.headers.setdefault("X-Request-ID", request.state.request_id)
        if request.url.path.startswith(("/v1/", "/internal/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _error(request, exc.status, exc.code, exc.message, exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Field locations and rule text only; submitted values are never echoed back.
        details = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:5])
        return _error(request, 422, "validation_error", f"Request is not valid. {details}", False)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _error(request, exc.status_code, code, str(exc.detail), False)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.error(
            "unhandled error type=%s request_id=%s",
            type(exc).__name__,
            getattr(request.state, "request_id", ""),
        )
        return _error(request, 500, "internal_error", "Something went wrong. Nothing has been concluded.", True)

    def principal(authorization: Annotated[str | None, Header()] = None) -> Principal:
        return container.authenticator.authenticate(authorization)

    def idem(idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None) -> str:
        if not idempotency_key:
            raise ApiError(400, "missing_idempotency_key", "The Idempotency-Key header is required.")
        return idempotency_key

    Who = Annotated[Principal, Depends(principal)]
    Key = Annotated[str, Depends(idem)]
    svc: AssessmentService = container.assessments

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    def readyz() -> JSONResponse:
        try:
            container.db.ping()
        except Exception:
            return JSONResponse({"status": "unavailable", "database": "down"}, status_code=503)
        return JSONResponse(
            {
                "status": "ready",
                "database": "up",
                "clinical_mode": settings.clinical_mode_enabled,
                "release": container.bundle.rules_version,
                "synthetic_release": container.bundle.synthetic,
            }
        )

    @app.post("/v1/sessions", status_code=201, operation_id="startAssessment")
    def start_assessment(body: sc.SessionCreate, who: Who, key: Key) -> JSONResponse:
        return JSONResponse(svc.start_session(who, body, key), status_code=201)

    @app.get("/v1/sessions/{session_id}", operation_id="getSession")
    def get_session(session_id: uuid.UUID, who: Who) -> JSONResponse:
        return JSONResponse(svc.get_session(who, session_id))

    @app.delete("/v1/sessions/{session_id}", operation_id="deleteSession")
    def delete_session(session_id: uuid.UUID, who: Who, key: Key) -> JSONResponse:
        return JSONResponse(svc.delete_session(who, session_id, key))

    @app.post("/v1/sessions/{session_id}/observations", operation_id="submitObservations")
    def submit_observations(session_id: uuid.UUID, body: sc.ObservationSubmit, who: Who, key: Key) -> JSONResponse:
        return JSONResponse(svc.submit_observations(who, session_id, body, key))

    @app.post("/v1/sessions/{session_id}/answers", operation_id="submitAnswer")
    def submit_answer(session_id: uuid.UUID, body: sc.AnswerSubmit, who: Who, key: Key) -> JSONResponse:
        return JSONResponse(svc.submit_answer(who, session_id, body, key))

    @app.post("/v1/sessions/{session_id}/assessments", operation_id="assessSession")
    def assess_session(session_id: uuid.UUID, body: sc.AssessmentRequest, who: Who, key: Key) -> JSONResponse:
        return JSONResponse(svc.assess_session(who, session_id, body, key))

    @app.get("/v1/sessions/{session_id}/next-question", operation_id="getNextQuestion")
    def get_next_question(
        session_id: uuid.UUID, who: Who, observation_version: Annotated[int, Query(ge=0)]
    ) -> Response:
        question = svc.get_next_question(who, session_id, observation_version)
        return Response(status_code=204) if question is None else JSONResponse(question)

    @app.post("/v1/sessions/{session_id}/summary", operation_id="createConsultationSummary")
    def create_summary(session_id: uuid.UUID, body: sc.AssessmentRequest, who: Who, key: Key) -> JSONResponse:
        return JSONResponse(svc.create_summary(who, session_id, body, key))

    # Extension beyond specs/openapi.json (see docs/DECISIONS.md): reviewed-only condition text.
    @app.get("/v1/conditions/{disease_id}", operation_id="getConditionInformation")
    def get_condition(disease_id: str, who: Who) -> JSONResponse:
        return JSONResponse(container.knowledge.get_condition_information(who, disease_id))

    # Internal reviewer workspace: requires the reviewer role from the verified token.
    @app.get("/internal/v1/review/overview")
    def review_overview(who: Who) -> JSONResponse:
        return JSONResponse(container.review.overview(who))

    @app.get("/internal/v1/review/disease-mappings")
    def review_disease_mappings(
        who: Who, status: str | None = None, q: str | None = None, limit: int = 50, offset: int = 0
    ) -> JSONResponse:
        return JSONResponse(container.review.list_disease_mappings(who, status=status, q=q, limit=limit, offset=offset))

    @app.get("/internal/v1/review/feature-mappings")
    def review_feature_mappings(
        who: Who,
        status: str | None = None,
        q: str | None = None,
        conflicts_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> JSONResponse:
        return JSONResponse(
            container.review.list_feature_mappings(
                who, status=status, q=q, conflicts_only=conflicts_only, limit=limit, offset=offset
            )
        )

    @app.get("/internal/v1/review/statements")
    def review_statements(
        who: Who,
        status: str | None = None,
        statement_type: str | None = None,
        disease_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> JSONResponse:
        return JSONResponse(
            container.review.list_statements(
                who,
                status=status,
                statement_type=statement_type,
                disease_id=disease_id,
                limit=limit,
                offset=offset,
            )
        )

    @app.get("/internal/v1/review/relation-suggestions")
    def review_relation_suggestions(
        who: Who,
        status: str | None = None,
        relation: str | None = None,
        subject_type: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> JSONResponse:
        return JSONResponse(
            container.review.list_relation_suggestions(
                who, status=status, relation=relation, subject_type=subject_type, q=q, limit=limit, offset=offset
            )
        )

    @app.get("/internal/v1/review/terminology-links")
    def review_terminology_links(
        who: Who,
        status: str | None = None,
        system: str | None = None,
        subject_type: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> JSONResponse:
        return JSONResponse(
            list_terminology_links(
                container.db,
                who,
                status=status,
                system=system,
                subject_type=subject_type,
                q=q,
                limit=limit,
                offset=offset,
            )
        )

    @app.get("/internal/v1/review/rules")
    def review_rules(
        who: Who, bundle_id: str | None = None, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> JSONResponse:
        return JSONResponse(
            list_rules(container.db, who, bundle_id=bundle_id, status=status, limit=limit, offset=offset)
        )

    @app.get("/internal/v1/review/diseases/{disease_id}/history")
    def review_disease_history(disease_id: str, who: Who) -> JSONResponse:
        return JSONResponse(disease_merges.state(container.db, who, disease_id))

    @app.post("/internal/v1/review/disease-merges")
    def review_disease_merge(body: DiseaseMerge, who: Who) -> JSONResponse:
        return JSONResponse(
            disease_merges.merge(
                container.db,
                who,
                source_id=body.source_disease_id,
                target_id=body.target_disease_id,
                note=body.note,
                kept_name=body.kept_name,
            )
        )

    @app.post("/internal/v1/review/disease-splits")
    def review_disease_split(body: DiseaseSplit, who: Who) -> JSONResponse:
        return JSONResponse(disease_merges.split(container.db, who, disease_id=body.disease_id, note=body.note))

    @app.get("/internal/v1/review/releases")
    def review_releases(who: Who) -> JSONResponse:
        return JSONResponse(releases.list_releases(container.db, who))

    @app.get("/internal/v1/review/releases/preview")
    def review_release_preview(who: Who, bundle_id: str) -> JSONResponse:
        return JSONResponse(releases.preview(container.db, who, bundle_id))

    @app.post("/internal/v1/review/releases")
    def review_release_publish(body: ReleasePublish, who: Who) -> JSONResponse:
        return JSONResponse(releases.publish(container.db, who, bundle_id=body.bundle_id, note=body.note))

    @app.post("/internal/v1/review/releases/current")
    def review_release_current(body: ReleaseSwitch, who: Who) -> JSONResponse:
        return JSONResponse(releases.make_current(container.db, who, release_id=body.release_id, note=body.note))

    @app.post("/internal/v1/review/decisions")
    def review_decision(body: ReviewDecision, who: Who) -> JSONResponse:
        return JSONResponse(
            container.review.record_review(
                who,
                target_type=body.target_type,
                target_id=body.target_id,
                note=body.note,
                status=body.status,
            )
        )

    @app.get("/internal/v1/review/features")
    def review_features(
        who: Who,
        status: str | None = None,
        kind: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> JSONResponse:
        return JSONResponse(
            published_mappings.list_features(
                container.db, who, status=status, kind=kind, q=q, limit=limit, offset=offset
            )
        )

    @app.get("/internal/v1/review/diseases")
    def review_diseases(
        who: Who, status: str | None = None, q: str | None = None, limit: int = 50, offset: int = 0
    ) -> JSONResponse:
        return JSONResponse(
            published_mappings.list_diseases(container.db, who, status=status, q=q, limit=limit, offset=offset)
        )

    @app.get("/internal/v1/review/mapping-releases")
    def review_mapping_releases(who: Who) -> JSONResponse:
        return JSONResponse(published_mappings.list_published(container.db, who))

    @app.get("/internal/v1/review/mapping-releases/preview")
    def review_mapping_release_preview(who: Who, mapping_release_id: str) -> JSONResponse:
        return JSONResponse(published_mappings.preview(container.db, who, mapping_release_id))

    @app.post("/internal/v1/review/mapping-releases")
    def review_mapping_release_publish(body: MappingPublish, who: Who) -> JSONResponse:
        return JSONResponse(
            published_mappings.publish(container.db, who, mapping_release_id=body.mapping_release_id, note=body.note)
        )

    @app.post("/internal/v1/review/mapping-releases/current")
    def review_mapping_release_current(body: ReleaseSwitch, who: Who) -> JSONResponse:
        return JSONResponse(
            published_mappings.make_current(container.db, who, release_id=body.release_id, note=body.note)
        )

    @app.get("/internal/v1/review/sources")
    def review_sources(who: Who) -> JSONResponse:
        return JSONResponse(published_knowledge.list_sources(container.db, who))

    @app.get("/internal/v1/review/evidence")
    def review_evidence(
        who: Who,
        status: str | None = None,
        evidence_type: str | None = None,
        disease_id: str | None = None,
        feature_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> JSONResponse:
        return JSONResponse(
            published_knowledge.list_evidence(
                container.db,
                who,
                status=status,
                evidence_type=evidence_type,
                disease_id=disease_id,
                feature_id=feature_id,
                limit=limit,
                offset=offset,
            )
        )

    @app.get("/internal/v1/review/knowledge-releases")
    def review_knowledge_releases(who: Who) -> JSONResponse:
        return JSONResponse(published_knowledge.list_published(container.db, who))

    @app.get("/internal/v1/review/knowledge-releases/preview")
    def review_knowledge_release_preview(who: Who, knowledge_release_id: str) -> JSONResponse:
        return JSONResponse(published_knowledge.preview(container.db, who, knowledge_release_id))

    @app.post("/internal/v1/review/knowledge-releases")
    def review_knowledge_release_publish(body: KnowledgePublish, who: Who) -> JSONResponse:
        return JSONResponse(
            published_knowledge.publish(
                container.db, who, knowledge_release_id=body.knowledge_release_id, note=body.note
            )
        )

    @app.post("/internal/v1/review/knowledge-releases/current")
    def review_knowledge_release_current(body: ReleaseSwitch, who: Who) -> JSONResponse:
        return JSONResponse(
            published_knowledge.make_current(container.db, who, release_id=body.release_id, note=body.note)
        )

    @app.get("/internal/v1/review/serving-bundle")
    def review_serving_bundle(who: Who) -> JSONResponse:
        return JSONResponse(serving_bundle.preview(container.db, who))

    @app.get("/internal/v1/review/response-texts")
    def review_response_texts(who: Who) -> JSONResponse:
        return JSONResponse(response_text_sets.list_sets(container.db, who))

    @app.get("/internal/v1/review/claims")
    def review_claims_list(
        who: Who,
        status: str | None = None,
        mark: str | None = None,
        statement_type: str | None = None,
        disease_id: str | None = None,
        statement_id: str | None = None,
        with_feature: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> JSONResponse:
        return JSONResponse(
            review_claims.list_claims(
                container.db,
                who,
                status=status,
                mark=mark,
                statement_type=statement_type,
                disease_id=disease_id,
                statement_id=statement_id,
                with_feature=with_feature,
                limit=limit,
                offset=offset,
            )
        )

    @app.post("/internal/v1/review/claims/{claim_id}/applicability")
    def review_claim_applicability(claim_id: str, body: ClaimApplicability, who: Who) -> JSONResponse:
        return JSONResponse(
            review_claims.set_applicability(container.db, who, claim_id=claim_id, text=body.text, note=body.note)
        )

    @app.get("/internal/v1/review/chunks")
    def review_chunks(
        who: Who,
        status: str | None = None,
        disease_id: str | None = None,
        q: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> JSONResponse:
        return JSONResponse(
            review_claims.list_chunks(
                container.db, who, status=status, disease_id=disease_id, q=q, limit=limit, offset=offset
            )
        )

    @app.get("/internal/v1/review/notes")
    def review_notes(target_type: str, target_id: str, who: Who) -> JSONResponse:
        return JSONResponse(list_notes(container.db, who, target_type=target_type, target_id=target_id))

    @app.post("/internal/v1/review/decisions/bulk")
    def review_decisions_bulk(body: BulkDecision, who: Who) -> JSONResponse:
        return JSONResponse(
            review_bulk.decide_many(
                container.db,
                who,
                target_type=body.target_type,
                target_ids=body.target_ids,
                note=body.note,
                status=body.status,
            )
        )

    @app.get("/internal/v1/review/link-proposals")
    def review_link_proposals(
        who: Who,
        status: str | None = None,
        system: str | None = None,
        basis: str | None = None,
        subject_type: str | None = None,
        decidable: bool | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> JSONResponse:
        return JSONResponse(
            review_proposals.list_link_proposals(
                container.db,
                who,
                status=status,
                system=system,
                basis=basis,
                subject_type=subject_type,
                decidable=decidable,
                q=q,
                limit=limit,
                offset=offset,
            )
        )

    return app


def app_factory() -> FastAPI:
    """uvicorn entry point: `uvicorn feeltriva_api.main:app_factory --factory`."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    return create_app()


# Request bodies added after the first ones stand here, at the end of the module, so that the lines above keep
# their numbers. The routes are defined when create_app runs, by which time these classes exist.
class MappingPublish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mapping_release_id: str
    note: str = Field(min_length=1, max_length=4000)


class KnowledgePublish(BaseModel):
    model_config = ConfigDict(extra="forbid")
    knowledge_release_id: str
    note: str = Field(min_length=1, max_length=4000)


class ClaimApplicability(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(default=None, max_length=500)
    note: str = Field(min_length=1, max_length=4000)


class BulkDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_type: str
    target_ids: list[str] = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=4000)
    status: str
