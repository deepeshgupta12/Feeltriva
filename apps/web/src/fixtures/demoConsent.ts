import type { Consent } from '@/api/types';
import { CONSENT_VERSION } from '@/config/consent';

/**
 * The terms the design demo shows before a sample check. Live mode shows the terms the service returns
 * (`GET /v1/consent`) and never these.
 *
 * The demo keeps nothing, so these say so; they are not a copy of the live terms.
 */
export const DEMO_CONSENT: Consent = {
  consent_id: 'demo-consent',
  version: CONSENT_VERSION,
  status: 'draft',
  language: 'en',
  region: 'IN',
  title: 'Before you start',
  sections: [
    {
      heading: 'What this is',
      paragraphs: [
        'Feeltriva helps you describe your symptoms, check what was understood, answer follow-up questions and prepare a summary for a consultation.',
        'Feeltriva does not confirm a diagnosis. A health professional may need to examine you or arrange tests.',
      ],
    },
    {
      heading: 'This is a design demo',
      paragraphs: [
        'It uses sample scenarios and does not assess real symptoms. Sample sessions reset when the page reloads, and no real account is created. Please don’t enter private health information into a shared preview.',
      ],
    },
    {
      heading: 'What happens to what you enter',
      paragraphs: [
        'What you enter is used only to run this check. It stays in this page’s memory and is gone when the page reloads.',
      ],
    },
  ],
  acknowledgement:
    'I understand that this is a demo, that it is not a medical assessment, and that Feeltriva does not confirm a diagnosis.',
  training: {
    label: 'You may also use my conversation to improve Feeltriva.',
    explanation:
      'This is a separate choice. It is off unless you tick it, and you can use Feeltriva without it. In the demo it has no effect: nothing you enter is used for training or analysis.',
  },
};
