import { useCallback, useEffect, useRef, useState } from 'react';

export type AsyncState<T> = { status: 'loading' } | { status: 'loaded'; data: T } | { status: 'failed' };

const LOADING = { status: 'loading' } as const;

/**
 * Loads data for a view. `key` identifies what is being loaded: when it changes the hook
 * reports `loading` again straight away, and a response for an older key is ignored.
 */
export function useAsync<T>(key: string, load: () => Promise<T>) {
  const [attempt, setAttempt] = useState(0);
  const requestKey = `${key}#${attempt}`;
  const [result, setResult] = useState<{ key: string; state: AsyncState<T> } | null>(null);

  const loadRef = useRef(load);
  useEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    let cancelled = false;
    loadRef.current().then(
      (data) => {
        if (!cancelled) setResult({ key: requestKey, state: { status: 'loaded', data } });
      },
      () => {
        if (!cancelled) setResult({ key: requestKey, state: { status: 'failed' } });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [requestKey]);

  const state: AsyncState<T> = result?.key === requestKey ? result.state : LOADING;
  const reload = useCallback(() => setAttempt((value) => value + 1), []);
  /** Replaces the loaded data, for example after a save returned the updated record. */
  const setData = useCallback(
    (data: T) => setResult({ key: requestKey, state: { status: 'loaded', data } }),
    [requestKey],
  );

  return { state, reload, setData };
}
