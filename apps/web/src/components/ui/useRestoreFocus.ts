import { useCallback, useRef } from 'react';

/**
 * Focus restoration for dialogs and sheets that are opened by state rather than by a
 * Radix `Trigger`. Radix only knows where to return focus when its own trigger is used,
 * so the element that had focus when the overlay opened is remembered here and focused
 * again when it closes.
 */
export function useRestoreFocus() {
  const opener = useRef<HTMLElement | null>(null);

  /** Called by Radix just before it moves focus into the overlay. */
  const onOpenAutoFocus = useCallback(() => {
    const active = document.activeElement;
    opener.current = active instanceof HTMLElement && active !== document.body ? active : null;
  }, []);

  /** Called by Radix when the overlay has closed. */
  const onCloseAutoFocus = useCallback((event: Event) => {
    const target = opener.current;
    opener.current = null;
    if (target && target.isConnected) {
      event.preventDefault();
      target.focus();
    }
  }, []);

  return { onOpenAutoFocus, onCloseAutoFocus };
}
