/**
 * Draft informational pages opened from the footer. All of it is placeholder copy awaiting
 * real policies: it is marked as a draft wherever it is shown and makes no legal,
 * compliance or clinical claims.
 */
export type InfoPageId = 'about' | 'privacy' | 'terms' | 'contact';

export interface InfoPage {
  id: InfoPageId;
  title: string;
  paragraphs: readonly string[];
}

export const INFO_PAGES: readonly InfoPage[] = [
  {
    id: 'about',
    title: 'About Feeltriva',
    paragraphs: [
      'Feeltriva is a symptom-assessment and care-navigation product in development. It helps people describe symptoms, review what was understood, answer follow-up questions and prepare a summary for a consultation.',
      'This is a design demo. It uses sample scenarios only, does not assess real symptoms and has not been clinically validated.',
      'Feeltriva does not confirm a diagnosis. A health professional may need to examine you or arrange tests.',
    ],
  },
  {
    id: 'privacy',
    title: 'Privacy',
    paragraphs: [
      'The privacy policy has not been written yet. This text is a placeholder and is not a commitment.',
      'In this demo, sample sessions are held in your browser’s memory and are cleared when the page reloads. The demo does not create an account and does not store health information in browser storage.',
      'Please do not enter private health information into a shared preview.',
    ],
  },
  {
    id: 'terms',
    title: 'Terms',
    paragraphs: [
      'Terms of use have not been written yet. This text is a placeholder and is not an agreement.',
      'The demo is provided to preview the design. It is not a medical service and must not be relied on for health decisions.',
    ],
  },
  {
    id: 'contact',
    title: 'Contact',
    paragraphs: [
      'Contact details have not been published yet.',
      'This demo cannot receive messages, and it is not monitored. It cannot respond to health concerns.',
    ],
  },
];
