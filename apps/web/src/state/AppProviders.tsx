import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router';

import { appConfig } from '@/config/env';
import { createCompletedSample, runScenario as loadScenario } from '@/demo/runScenario';
import type { ScenarioId } from '@/fixtures/scenarios';

import { DemoContext, type DemoState } from './demo';
import { readNavCollapsed, writeNavCollapsed } from './preferences';
import { PreferencesContext, type Preferences } from './preferencesContext';
import { createAppServices, ServicesContext, type AppServices } from './services';

interface AppProvidersProps {
  children: ReactNode;
  /** Tests inject their own services; the app builds them from public config. */
  services?: AppServices;
}

/** Wires services, demo controls and preferences. Must be rendered inside a router. */
export function AppProviders({ children, services: injected }: AppProvidersProps) {
  const [services] = useState<AppServices>(() => injected ?? createAppServices(appConfig));
  const { mock, registry, config } = services;
  const navigate = useNavigate();

  // --- Preferences -------------------------------------------------------
  const [navCollapsed, setNavCollapsedState] = useState<boolean>(() => readNavCollapsed());
  const [historyEnabled, setHistoryEnabled] = useState(true);
  const [trainingConsent, setTrainingConsent] = useState(false);

  const setNavCollapsed = useCallback((collapsed: boolean) => {
    setNavCollapsedState(collapsed);
    writeNavCollapsed(collapsed);
  }, []);

  const preferences = useMemo<Preferences>(
    () => ({
      navCollapsed,
      setNavCollapsed,
      historyEnabled,
      setHistoryEnabled,
      trainingConsent,
      setTrainingConsent,
    }),
    [navCollapsed, setNavCollapsed, historyEnabled, trainingConsent],
  );

  // --- Demo controls -----------------------------------------------------
  const [reviewerPreview, setReviewerPreview] = useState(false);
  const [activeScenario, setActiveScenario] = useState<ScenarioId | null>(null);
  const [scenarioLoading, setScenarioLoading] = useState(false);
  const [offline, setOfflineState] = useState(false);
  const [outage, setOutageState] = useState(false);

  const runScenario = useCallback(
    async (scenario: ScenarioId) => {
      if (!mock) {
        return;
      }
      setScenarioLoading(true);
      setOfflineState(false);
      try {
        const outcome = await loadScenario(scenario, { mock, registry, setReviewerPreview });
        setActiveScenario(scenario);
        setOutageState(mock.isOutage());
        void navigate(outcome.route);
      } finally {
        setScenarioLoading(false);
      }
    },
    [mock, registry, navigate],
  );

  const setOffline = useCallback(
    (next: boolean) => {
      mock?.setOffline(next);
      setOfflineState(next);
    },
    [mock],
  );

  const setOutage = useCallback(
    (next: boolean) => {
      mock?.setOutage(next);
      setOutageState(next);
    },
    [mock],
  );

  const simulateConcurrentUpdate = useCallback(
    (sessionId: string) => {
      mock?.simulateConcurrentUpdate(sessionId);
    },
    [mock],
  );

  const createSample = useCallback(async () => {
    if (!mock) {
      return null;
    }
    const controller = await createCompletedSample({ mock, registry, setReviewerPreview });
    return controller.sessionId;
  }, [mock, registry]);

  const resetDemo = useCallback(() => {
    mock?.reset();
    registry.clear();
    setActiveScenario(null);
    setOfflineState(false);
    setOutageState(false);
    setReviewerPreview(false);
  }, [mock, registry]);

  const demo = useMemo<DemoState>(
    () => ({
      toolsEnabled: config.demoTools,
      scenariosAvailable: mock !== null,
      activeScenario,
      scenarioLoading,
      runScenario,
      reviewerPreview,
      setReviewerPreview,
      offline,
      setOffline,
      outage,
      setOutage,
      simulateConcurrentUpdate,
      createCompletedSample: createSample,
      resetDemo,
    }),
    [
      config.demoTools,
      mock,
      activeScenario,
      scenarioLoading,
      runScenario,
      reviewerPreview,
      offline,
      setOffline,
      outage,
      setOutage,
      simulateConcurrentUpdate,
      createSample,
      resetDemo,
    ],
  );

  return (
    <ServicesContext.Provider value={services}>
      <PreferencesContext.Provider value={preferences}>
        <DemoContext.Provider value={demo}>{children}</DemoContext.Provider>
      </PreferencesContext.Provider>
    </ServicesContext.Provider>
  );
}
