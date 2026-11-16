import type { AssessmentService } from '@/api/assessmentService';
import type { Session } from '@/api/types';

import { AssessmentController } from './AssessmentController';

export interface RegistryEntry {
  sessionId: string;
  controller: AssessmentController;
  createdAt: Date;
  /** Creation sequence, used to keep a stable newest-first order. */
  order: number;
  /** Title chosen by the user. Never derived from symptoms. */
  title: string;
  /** Whether the session appears in "Saved summaries" (the saved-history preference). */
  listed: boolean;
}

/**
 * In-memory index of the assessment sessions opened since the page loaded.
 *
 * This is the only place session view state lives. It is never written to localStorage,
 * sessionStorage, IndexedDB or a cache, so reloading the page clears every health detail.
 * (specs/openapi.json has no "list my sessions" endpoint; production history must come
 * from the authenticated backend.)
 */
export class SessionRegistry {
  private readonly service: AssessmentService;
  private readonly entries = new Map<string, RegistryEntry>();
  private readonly unsubscribers = new Map<string, () => void>();
  private readonly listeners = new Set<() => void>();
  private readonly now: () => Date;
  private snapshot: readonly RegistryEntry[] = [];
  private createdCount = 0;
  private order = 0;

  constructor(service: AssessmentService, options: { now?: () => Date } = {}) {
    this.service = service;
    this.now = options.now ?? (() => new Date());
  }

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  /** Newest first. A new array identity is produced whenever any session changes. */
  readonly getSnapshot = (): readonly RegistryEntry[] => this.snapshot;

  /** Registers a session that was just created with `startSession`. */
  create(session: Session, options: { listed?: boolean; title?: string } = {}): AssessmentController {
    const controller = new AssessmentController(this.service, session.session_id, session);
    this.createdCount += 1;
    this.order += 1;
    this.add({
      sessionId: session.session_id,
      controller,
      createdAt: this.now(),
      order: this.order,
      title: options.title ?? `Sample assessment ${this.createdCount}`,
      listed: options.listed ?? true,
    });
    return controller;
  }

  /** Returns the controller for a session, loading it from the service when unknown. */
  getOrLoad(sessionId: string): AssessmentController {
    const existing = this.entries.get(sessionId);
    if (existing) {
      return existing.controller;
    }
    const controller = new AssessmentController(this.service, sessionId);
    this.order += 1;
    this.entries.set(sessionId, {
      sessionId,
      controller,
      createdAt: this.now(),
      order: this.order,
      title: 'Assessment',
      // Sessions opened by URL are not added to the history list.
      listed: false,
    });
    this.unsubscribers.set(
      sessionId,
      controller.subscribe(() => this.emit()),
    );
    // This can be called while React is rendering, so notifying subscribers and starting
    // the request are deferred until after the current render.
    queueMicrotask(() => {
      this.emit();
      void controller.load();
    });
    return controller;
  }

  get(sessionId: string): RegistryEntry | undefined {
    return this.entries.get(sessionId);
  }

  rename(sessionId: string, title: string): void {
    const entry = this.entries.get(sessionId);
    const trimmed = title.trim();
    if (entry && trimmed.length > 0) {
      this.entries.set(sessionId, { ...entry, title: trimmed.slice(0, 80) });
      this.emit();
    }
  }

  /** Removes an entry from memory (for example after its deletion receipt was dismissed). */
  forget(sessionId: string): void {
    this.unsubscribers.get(sessionId)?.();
    this.unsubscribers.delete(sessionId);
    if (this.entries.delete(sessionId)) {
      this.emit();
    }
  }

  /** Most recent session that is still usable, for the "This conversation" link. */
  latestActiveSessionId(): string | null {
    for (const entry of this.snapshot) {
      const load = entry.controller.getSnapshot().load;
      if (load === 'ready' || load === 'loading' || load === 'idle') {
        return entry.sessionId;
      }
    }
    return null;
  }

  /** Drops everything held in memory. Does not delete anything on the service. */
  clear(): void {
    for (const unsubscribe of this.unsubscribers.values()) {
      unsubscribe();
    }
    this.unsubscribers.clear();
    this.entries.clear();
    this.emit();
  }

  private add(entry: RegistryEntry): void {
    this.entries.set(entry.sessionId, entry);
    this.unsubscribers.set(
      entry.sessionId,
      entry.controller.subscribe(() => this.emit()),
    );
    this.emit();
  }

  private emit(): void {
    this.snapshot = [...this.entries.values()].sort((a, b) => b.order - a.order);
    for (const listener of this.listeners) {
      listener();
    }
  }
}
