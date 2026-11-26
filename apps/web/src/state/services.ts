import { createContext, useContext } from 'react';

import type { AssessmentService } from '@/api/assessmentService';
import {
  FixtureConditionInfoService,
  HttpConditionInfoService,
  type ConditionInfoService,
} from '@/api/conditionInfoService';
import { createAuthTokenProvider } from '@/api/http/auth';
import { HttpAssessmentService } from '@/api/http/HttpAssessmentService';
import { HttpLiveReviewApi, type LiveReviewApi } from '@/api/liveReview';
import { MockAssessmentService } from '@/api/mock/MockAssessmentService';
import { FixtureReviewService, type ReviewService } from '@/api/reviewService';
import type { AppConfig } from '@/config/env';

import { SessionRegistry } from './SessionRegistry';

export interface AppServices {
  config: AppConfig;
  /** The assessment backend: mock or HTTP, chosen by VITE_SERVICE_MODE. */
  assessment: AssessmentService;
  /** The mock instance when running in mock mode (exposes demo controls); otherwise null. */
  mock: MockAssessmentService | null;
  /** Fixture-backed until the API has endpoints for these. */
  conditions: ConditionInfoService;
  review: ReviewService;
  /** The review workspace against the running API. Used in http mode; the fixtures above serve the demo. */
  liveReview: LiveReviewApi;
  registry: SessionRegistry;
}

/** Simulated latency in the running demo, so loading states are visible. */
export const DEMO_LATENCY_MS = 350;

export function createAppServices(config: AppConfig, overrides: Partial<AppServices> = {}): AppServices {
  const mock =
    overrides.mock !== undefined
      ? overrides.mock
      : config.serviceMode === 'mock'
        ? new MockAssessmentService({ latencyMs: DEMO_LATENCY_MS })
        : null;

  // One token for everything a person does in a visit: the assessment and the condition pages it links to.
  const getAuthToken = createAuthTokenProvider({ devAuth: config.devAuth });
  const assessment =
    overrides.assessment ?? mock ?? new HttpAssessmentService({ baseUrl: config.apiBaseUrl, getAuthToken });

  return {
    config,
    assessment,
    mock,
    // The design demo shows labelled placeholders; live mode reads only what the service has published.
    conditions:
      overrides.conditions ??
      (config.serviceMode === 'http'
        ? new HttpConditionInfoService({ baseUrl: config.apiBaseUrl, getAuthToken })
        : new FixtureConditionInfoService()),
    review: overrides.review ?? new FixtureReviewService(),
    liveReview:
      overrides.liveReview ?? new HttpLiveReviewApi({ baseUrl: config.apiBaseUrl, devReviewer: config.devReviewer }),
    registry: overrides.registry ?? new SessionRegistry(assessment),
  };
}

export const ServicesContext = createContext<AppServices | null>(null);

export function useServices(): AppServices {
  const services = useContext(ServicesContext);
  if (!services) {
    throw new Error('useServices must be used inside <AppProviders>.');
  }
  return services;
}
