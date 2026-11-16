import { SAMPLE_CONDITIONS } from '@/fixtures/conditions';

import type { Evidence } from './types';

/**
 * Reviewed condition information.
 *
 * specs/openapi.json has no REST endpoint for this yet (the MCP contract names
 * `get_condition_information`), so the only implementation serves labelled placeholder
 * fixtures. When an endpoint exists, add an HTTP implementation of this interface.
 */
export interface ConditionInfo {
  disease_id: string;
  name: string;
  /** True when the content is a demo placeholder rather than reviewed clinical content. */
  is_sample: boolean;
  knowledge_release: string;
  /** Each section is optional: a section with no reviewed content is omitted, never invented. */
  overview?: string;
  symptoms?: readonly string[];
  causes?: readonly string[];
  management?: readonly string[];
  questions_for_clinician?: readonly string[];
  sources: readonly Evidence[];
}

export interface ConditionInfoService {
  /** Resolves `null` when no reviewed information exists for the id. */
  getCondition(diseaseId: string): Promise<ConditionInfo | null>;
}

export class FixtureConditionInfoService implements ConditionInfoService {
  private readonly conditions: readonly ConditionInfo[];

  constructor(conditions: readonly ConditionInfo[] = SAMPLE_CONDITIONS) {
    this.conditions = conditions;
  }

  getCondition(diseaseId: string): Promise<ConditionInfo | null> {
    const match = this.conditions.find((condition) => condition.disease_id === diseaseId);
    return Promise.resolve(match ? structuredClone(match) : null);
  }
}
