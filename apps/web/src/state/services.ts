import { createContext, useContext } from 'react';

import type { AssessmentService } from '@/api/assessmentService';
import { FixtureConditionInfoService, type ConditionInfoService } from '@/api/conditionInfoService';
import { createAuthTokenProvider } from '@/api/http/auth';
import { HttpAssessmentService } from '@/api/http/HttpAssessmentService';
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

  const assessment =
    overrides.assessment ??
    mock ??
    new HttpAssessmentService({
      baseUrl: config.apiBaseUrl,
      getAuthToken: createAuthTokenProvider({ devAuth: config.devAuth }),
    });

  return {
    config,
    assessment,
    mock,
    conditions: overrides.conditions ?? new FixtureConditionInfoService(),
    review: overrides.review ?? new FixtureReviewService(),
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
