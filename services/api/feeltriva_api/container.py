from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from feeltriva_clinical import ReleaseBundle, load_bundle, load_fixture_bundle
from feeltriva_inference import BundleCandidateProvider
from feeltriva_llm import MockExtractor
from feeltriva_retrieval import BundleEvidenceProvider

from .auth import Authenticator
from .crypto import FieldCipher
from .db import Database
from .rate_limit import RateLimiter
from .review import KnowledgeService, ReviewService
from .service import AssessmentService
from .settings import Settings


@dataclass
class Container:
    settings: Settings
    db: Database
    bundle: ReleaseBundle
    assessments: AssessmentService
    review: ReviewService
    knowledge: KnowledgeService
    authenticator: Authenticator
    limiter: RateLimiter


def load_release(settings: Settings) -> ReleaseBundle:
    """Fixture bundle unless clinical mode is on; clinical mode only loads a fully approved,
    non-synthetic bundle and refuses to start otherwise."""
    if not settings.clinical_mode_enabled:
        return load_fixture_bundle()
    if settings.llm_provider == "mock":
        raise RuntimeError("clinical mode cannot run with the mock extraction provider")
    return load_bundle(Path(settings.rule_bundle_path), clinical_mode=True)


def build_container(settings: Settings, db: Database | None = None) -> Container:
    if not settings.database_url and db is None:
        raise RuntimeError("DATABASE_URL is required")
    db = db or Database(settings.database_url)
    bundle = load_release(settings)
    clinical = settings.clinical_mode_enabled
    if clinical:
        # Clinical mode serves only what was published: the rules loaded must be the current release (M2.5b).
        # ... and the whole bundle must be what the current releases give (M2.5f).
        from .releases import verify_published
        from .serving_bundle import verify_serving

        verify_published(db, bundle)
        verify_serving(db, bundle)
    assessments = AssessmentService(
        db=db,
        settings=settings,
        cipher=FieldCipher(settings),
        bundle=bundle,
        extractor=MockExtractor(),
        candidates=BundleCandidateProvider(bundle, clinical_mode=clinical),
        evidence=BundleEvidenceProvider(bundle, clinical_mode=clinical),
    )
    return Container(
        settings,
        db,
        bundle,
        assessments,
        ReviewService(db),
        KnowledgeService(db),
        Authenticator(settings),
        RateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds),
    )
