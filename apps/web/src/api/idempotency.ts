import { stableStringify } from '@/lib/stableStringify';
import { uuid } from '@/lib/uuid';

/** Identifies "the same operation with the same payload". */
export function operationFingerprint(method: string, path: string, body: unknown): string {
  return `${method.toUpperCase()} ${path} ${stableStringify(body ?? null)}`;
}

/**
 * Hands out Idempotency-Key values.
 *
 * - The first attempt of an operation gets a fresh key.
 * - A retry of the same payload gets the same key until the operation is released.
 * - Callers release the key once the server has answered definitively (success, or an
 *   error that will not succeed on retry), so the next submission is a new operation.
 *
 * Keys live in memory only. Fingerprints can contain what the user typed, so nothing here
 * is ever written to browser storage.
 */
export class IdempotencyKeyStore {
  private readonly keys = new Map<string, string>();
  private readonly generate: () => string;
  private readonly maxEntries: number;

  constructor(options: { generate?: () => string; maxEntries?: number } = {}) {
    this.generate = options.generate ?? uuid;
    this.maxEntries = options.maxEntries ?? 200;
  }

  keyFor(fingerprint: string): string {
    const existing = this.keys.get(fingerprint);
    if (existing !== undefined) {
      return existing;
    }
    const key = this.generate();
    this.keys.set(fingerprint, key);
    if (this.keys.size > this.maxEntries) {
      const oldest = this.keys.keys().next().value;
      if (oldest !== undefined) {
        this.keys.delete(oldest);
      }
    }
    return key;
  }

  release(fingerprint: string): void {
    this.keys.delete(fingerprint);
  }

  has(fingerprint: string): boolean {
    return this.keys.has(fingerprint);
  }
}

/**
 * Shared mutation discipline for every AssessmentService implementation:
 * one Idempotency-Key per operation, the same key for a retry of the same payload, and
 * no second request while an identical one is still pending.
 */
export class MutationGate {
  private readonly keys: IdempotencyKeyStore;
  private readonly inFlight = new Map<string, Promise<unknown>>();

  constructor(keys: IdempotencyKeyStore = new IdempotencyKeyStore()) {
    this.keys = keys;
  }

  /**
   * @param send performs the request with the given Idempotency-Key.
   * @param keepKeyOnError decides whether a failed attempt keeps its key for a retry.
   */
  run<T>(
    fingerprint: string,
    send: (idempotencyKey: string) => Promise<T>,
    keepKeyOnError: (error: unknown) => boolean,
  ): Promise<T> {
    const pending = this.inFlight.get(fingerprint);
    if (pending !== undefined) {
      return pending as Promise<T>;
    }

    const idempotencyKey = this.keys.keyFor(fingerprint);
    const promise = send(idempotencyKey).then(
      (result) => {
        this.keys.release(fingerprint);
        return result;
      },
      (error: unknown) => {
        if (!keepKeyOnError(error)) {
          this.keys.release(fingerprint);
        }
        throw error;
      },
    );

    this.inFlight.set(fingerprint, promise);
    const clear = () => {
      if (this.inFlight.get(fingerprint) === promise) {
        this.inFlight.delete(fingerprint);
      }
    };
    promise.then(clear, clear);
    return promise;
  }
}
