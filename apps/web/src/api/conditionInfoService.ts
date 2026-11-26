import { SAMPLE_CONDITIONS } from '@/fixtures/conditions';

import type { AuthTokenProvider } from './http/auth';
import type { Evidence } from './types';

/**
 * Reviewed condition information.
 *
 * Two implementations. In the design demo the page shows labelled placeholder fixtures. In live
 * mode it reads `GET /v1/conditions/{disease_id}` of the service (M2.9a), which answers only from
 * what has been reviewed, approved and published; a condition without such content is answered
 * with "not available", and the page then shows nothing rather than an unreviewed description.
 * The route is not in specs/openapi.json yet, so its answer is typed here by hand.
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

interface HttpConditionInfoOptions {
  baseUrl: string;
  /** Supplies the bearer token; see src/api/http/auth.ts. */
  getAuthToken: AuthTokenProvider;
  fetchImpl?: typeof fetch;
}

/** What the service answers: the condition and its published texts, each with the records it rests on. */
interface ServedCondition {
  disease_id: string;
  name: string;
  definition: string | null;
  statements: ReadonlyArray<{
    statement_id: string;
    statement_type: string;
    text: string;
    sources: ReadonlyArray<{ record_id: string; source_url: string | null }>;
  }>;
}

/** The kinds of text the service publishes, and the section of the page each belongs to. */
const SECTION_OF: Record<string, 'overview' | 'symptoms' | 'causes' | 'management'> = {
  description: 'overview',
  symptom: 'symptoms',
  cause: 'causes',
  treatment: 'management',
  management: 'management',
  prevention: 'management',
};

function sourceTitle(url: string | null): string {
  if (!url) {
    return 'Source record';
  }
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return 'Source record';
  }
}

/** The service's answer laid out as the page shows it. Nothing is added: a section without a text is left out. */
export function toConditionInfo(served: ServedCondition): ConditionInfo {
  const sections: Record<'overview' | 'symptoms' | 'causes' | 'management', string[]> = {
    overview: served.definition ? [served.definition] : [],
    symptoms: [],
    causes: [],
    management: [],
  };
  const sources: Evidence[] = [];
  for (const statement of served.statements) {
    const section = SECTION_OF[statement.statement_type];
    if (!section) {
      continue; // a kind of text this page has no section for is not shown under another heading
    }
    sections[section].push(statement.text);
    for (const source of statement.sources) {
      sources.push({
        evidence_id: `${statement.statement_id}:${source.record_id}`,
        source_title: sourceTitle(source.source_url),
        source_url: source.source_url,
        excerpt: statement.text,
        knowledge_release: '',
      });
    }
  }
  return {
    disease_id: served.disease_id,
    name: served.name,
    is_sample: false,
    knowledge_release: '',
    overview: sections.overview.length > 0 ? sections.overview.join(' ') : undefined,
    symptoms: sections.symptoms.length > 0 ? sections.symptoms : undefined,
    causes: sections.causes.length > 0 ? sections.causes : undefined,
    management: sections.management.length > 0 ? sections.management : undefined,
    sources,
  };
}

export class HttpConditionInfoService implements ConditionInfoService {
  private readonly baseUrl: string;
  private readonly getAuthToken: AuthTokenProvider;
  private readonly fetchImpl: typeof fetch;

  constructor(options: HttpConditionInfoOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '');
    this.getAuthToken = options.getAuthToken;
    this.fetchImpl = options.fetchImpl ?? ((input, init) => globalThis.fetch(input, init));
  }

  async getCondition(diseaseId: string): Promise<ConditionInfo | null> {
    const token = await this.getAuthToken();
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    // The API is called with a bearer token, never ambient cookies.
    const response = await this.fetchImpl(`${this.baseUrl}/v1/conditions/${encodeURIComponent(diseaseId)}`, {
      headers,
      credentials: 'omit',
    });
    if (response.status === 404) {
      return null; // nothing reviewed and published for this condition
    }
    if (!response.ok) {
      throw new Error(`Condition information could not be loaded (${response.status}).`);
    }
    return toConditionInfo((await response.json()) as ServedCondition);
  }
}
