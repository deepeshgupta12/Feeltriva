/**
 * Placeholder condition pages for the two illustrative possibilities. Every sentence is a
 * labelled placeholder. Sections with no reviewed content are simply absent so the page
 * hides them rather than filling the gap.
 */
import type { ConditionInfo } from '@/api/conditionInfoService';

import { DEMO_KNOWLEDGE_RELEASE, SAMPLE_CANDIDATES, SAMPLE_EVIDENCE } from './sampleContent';

export const SAMPLE_CONDITIONS: readonly ConditionInfo[] = [
  {
    disease_id: SAMPLE_CANDIDATES.a.disease_id,
    name: SAMPLE_CANDIDATES.a.name,
    is_sample: true,
    knowledge_release: DEMO_KNOWLEDGE_RELEASE,
    overview:
      'Placeholder overview. A reviewed, plain-language description of the condition appears here in the live service.',
    symptoms: [
      'Placeholder: a reviewed symptom description would be listed here.',
      'Placeholder: a second reviewed symptom description.',
    ],
    causes: ['Placeholder: reviewed information about causes and risk context.'],
    management: [
      'Placeholder: reviewed, source-linked educational information about management. It is general information, not personal advice.',
    ],
    questions_for_clinician: [
      'Placeholder: a question you could ask a health professional.',
      'Placeholder: another question you could ask.',
    ],
    sources: [SAMPLE_EVIDENCE.first, SAMPLE_EVIDENCE.second],
  },
  {
    // Only an overview and one source have "reviewed" placeholder content here, to show
    // that sections without content are hidden.
    disease_id: SAMPLE_CANDIDATES.b.disease_id,
    name: SAMPLE_CANDIDATES.b.name,
    is_sample: true,
    knowledge_release: DEMO_KNOWLEDGE_RELEASE,
    overview:
      'Placeholder overview for the second illustrative possibility. Other sections have no reviewed content and are not shown.',
    sources: [SAMPLE_EVIDENCE.second],
  },
];
