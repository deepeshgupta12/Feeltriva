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

from . import schemas as sc
from .auth import Principal
from .container import Container, build_container
from .errors import ApiError
from .review import list_terminology_links
from .service import AssessmentService
from .settings import Settings, get_settings

log = logging.getLogger("feeltriva.api")


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_type: str
    target_id: str
    note: str = Field(min_length=1, max_length=4000)
    status: str | None = None


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

    return app


def app_factory() -> FastAPI:
    """uvicorn entry point: `uvicorn feeltriva_api.main:app_factory --factory`."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    return create_app()
