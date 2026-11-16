import { useEffect, useMemo, useSyncExternalStore } from 'react';

import type { AssessmentController, AssessmentViewState } from './AssessmentController';
import { useDemo } from './demo';
import type { RegistryEntry } from './SessionRegistry';
import { useServices } from './services';

/** Subscribes to one assessment session, loading it from the service when needed. */
export function useAssessment(sessionId: string): { controller: AssessmentController; state: AssessmentViewState } {
  const { registry } = useServices();
  const controller = useMemo(() => registry.getOrLoad(sessionId), [registry, sessionId]);
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  return { controller, state };
}

/** Sessions opened since the page loaded, newest first. */
export function useRegistryEntries(): readonly RegistryEntry[] {
  const { registry } = useServices();
  return useSyncExternalStore(registry.subscribe, registry.getSnapshot, registry.getSnapshot);
}

function subscribeToConnectivity(listener: () => void): () => void {
  window.addEventListener('online', listener);
  window.addEventListener('offline', listener);
  return () => {
    window.removeEventListener('online', listener);
    window.removeEventListener('offline', listener);
  };
}

/** Browser connectivity, combined with the demo's "Simulate offline" switch. */
export function useOnlineStatus(): boolean {
  const browserOnline = useSyncExternalStore(
    subscribeToConnectivity,
    () => navigator.onLine,
    () => true,
  );
  const { offline } = useDemo();
  return browserOnline && !offline;
}

const SITE_NAME = 'Feeltriva';
const ROBOTS_META_ID = 'feeltriva-robots';

/**
 * Sets a generic document title and, for private routes, a `noindex` robots tag.
 * Titles describe the screen only. Never pass symptoms or other health details here.
 */
export function usePageMeta(title: string, options: { noindex?: boolean } = {}): void {
  const noindex = options.noindex ?? false;
  useEffect(() => {
    document.title = title ? `${title} · ${SITE_NAME}` : SITE_NAME;
  }, [title]);

  useEffect(() => {
    if (!noindex) {
      return;
    }
    let meta = document.getElementById(ROBOTS_META_ID) as HTMLMetaElement | null;
    const created = meta === null;
    if (!meta) {
      meta = document.createElement('meta');
      meta.id = ROBOTS_META_ID;
      meta.name = 'robots';
      document.head.appendChild(meta);
    }
    meta.content = 'noindex, nofollow';
    return () => {
      if (created) {
        meta.remove();
      }
    };
  }, [noindex]);
}
