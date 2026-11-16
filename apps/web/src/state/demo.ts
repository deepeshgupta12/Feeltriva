import { createContext, useContext } from 'react';

import type { ScenarioId } from '@/fixtures/scenarios';

export interface DemoState {
  /** Whether the demo tools (scenario switcher, reviewer preview switch) are offered. */
  toolsEnabled: boolean;
  /** Scenarios need the in-memory mock service. */
  scenariosAvailable: boolean;
  activeScenario: ScenarioId | null;
  scenarioLoading: boolean;
  runScenario: (scenario: ScenarioId) => Promise<void>;
  /**
   * Reviewer preview. This is a demo convenience, NOT authorization: production must
   * enforce reviewer roles on the backend and protect the routes.
   */
  reviewerPreview: boolean;
  setReviewerPreview: (enabled: boolean) => void;
  /** Simulated offline (mock mode). */
  offline: boolean;
  setOffline: (offline: boolean) => void;
  /** Simulated assessment outage (mock mode). */
  outage: boolean;
  setOutage: (outage: boolean) => void;
  /** Simulates a change from another tab for the given session (mock mode). */
  simulateConcurrentUpdate: (sessionId: string) => void;
  /** Creates one completed sample assessment (mock mode). Resolves its session id. */
  createCompletedSample: () => Promise<string | null>;
  /** Clears every in-memory sample session and demo switch. */
  resetDemo: () => void;
}

export const DemoContext = createContext<DemoState | null>(null);

export function useDemo(): DemoState {
  const demo = useContext(DemoContext);
  if (!demo) {
    throw new Error('useDemo must be used inside <AppProviders>.');
  }
  return demo;
}
