import { render, type RenderResult } from '@testing-library/react';
import userEvent, { type UserEvent } from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';

import { MockAssessmentService } from '@/api/mock/MockAssessmentService';
import { App } from '@/App';
import type { AppConfig } from '@/config/env';
import { runScenario } from '@/demo/runScenario';
import type { ScenarioId } from '@/fixtures/scenarios';
import { AppProviders } from '@/state/AppProviders';
import { createAppServices, type AppServices } from '@/state/services';

export const TEST_CONFIG: AppConfig = {
  serviceMode: 'mock',
  apiBaseUrl: 'http://localhost:8000',
  devAuth: false,
  demoTools: true,
};

/** Services backed by the in-memory mock with no simulated latency. */
export function createTestServices(): AppServices & { mock: MockAssessmentService } {
  const mock = new MockAssessmentService({ latencyMs: 0 });
  const services = createAppServices(TEST_CONFIG, { mock });
  return { ...services, mock };
}

export interface RenderedApp extends RenderResult {
  services: AppServices & { mock: MockAssessmentService };
  user: UserEvent;
}

/** Renders the whole application at `route`. */
export function renderApp(route: string, services = createTestServices()): RenderedApp {
  const user = userEvent.setup();
  const result = render(
    <MemoryRouter initialEntries={[route]}>
      <AppProviders services={services}>
        <App />
      </AppProviders>
    </MemoryRouter>,
  );
  return { ...result, services, user };
}

/** Loads a demo scenario into fresh services and returns where the scenario lands. */
export async function seedScenario(scenario: ScenarioId) {
  const services = createTestServices();
  const outcome = await runScenario(scenario, {
    mock: services.mock,
    registry: services.registry,
    setReviewerPreview: () => {},
  });
  const sessionId = outcome.route.split('/')[2] ?? '';
  return { services, route: outcome.route, sessionId };
}
