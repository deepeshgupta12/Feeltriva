import { createContext, useContext } from 'react';

export interface Preferences {
  /** Desktop navigation collapsed. The only preference persisted to localStorage. */
  navCollapsed: boolean;
  setNavCollapsed: (collapsed: boolean) => void;
  /** List new assessments under "Saved summaries". Held in memory in the demo. */
  historyEnabled: boolean;
  setHistoryEnabled: (enabled: boolean) => void;
  /** Separate from consent to use the service. Off by default; no effect in the demo. */
  trainingConsent: boolean;
  setTrainingConsent: (enabled: boolean) => void;
}

export const PreferencesContext = createContext<Preferences | null>(null);

export function usePreferences(): Preferences {
  const preferences = useContext(PreferencesContext);
  if (!preferences) {
    throw new Error('usePreferences must be used inside <AppProviders>.');
  }
  return preferences;
}
