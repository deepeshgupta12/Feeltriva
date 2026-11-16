/**
 * The only thing this app writes to browser storage: non-sensitive interface preferences.
 *
 * Health information (symptoms, answers, results, summaries, session ids) must never be
 * stored here or anywhere else that survives a reload. Add a key to this allow-list only
 * if its value says nothing about a person's health.
 */
export const NAV_COLLAPSED_KEY = 'feeltriva.ui.navCollapsed';

export const ALLOWED_STORAGE_KEYS: readonly string[] = [NAV_COLLAPSED_KEY];

export function readNavCollapsed(): boolean {
  try {
    return globalThis.localStorage.getItem(NAV_COLLAPSED_KEY) === 'true';
  } catch {
    // Storage can be unavailable (private mode, blocked cookies). The default is fine.
    return false;
  }
}

export function writeNavCollapsed(collapsed: boolean): void {
  try {
    globalThis.localStorage.setItem(NAV_COLLAPSED_KEY, collapsed ? 'true' : 'false');
  } catch {
    // Ignore: the preference simply will not persist.
  }
}
