import type { SummaryModel, SummarySection } from '@/lib/summaryModel';

import { LogoMark } from './Logo';

interface SummaryPreviewProps {
  model: SummaryModel;
}

function Section({ section }: { section: SummarySection }) {
  return (
    <section className="print-avoid-break">
      <h3 className="font-display text-lg font-bold text-ink">{section.title}</h3>
      {section.note ? <p className="text-sm text-ink-secondary">{section.note}</p> : null}
      {section.items.length > 0 ? (
        <ul className="mt-1.5 list-disc space-y-1 pl-5 text-ink">
          {section.items.map((item, index) => (
            <li key={`${section.id}-${index}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-1.5 text-ink-secondary">{section.emptyText}</p>
      )}
    </section>
  );
}

/**
 * The consultation summary as a print-friendly document. The demo label appears in both
 * the document header and footer so it survives printing and saving as PDF. What the
 * person reported is kept apart from the assessment's provisional output.
 */
export function SummaryPreview({ model }: SummaryPreviewProps) {
  const reported = model.sections.filter((section) => section.origin === 'reported_by_user');
  const fromAssessment = model.sections.filter((section) => section.origin === 'from_assessment');
  return (
    <article
      aria-label="Consultation summary document"
      className="print-document rounded-card border border-line bg-surface p-5 sm:p-8"
    >
      <header className="border-b border-line pb-4">
        <p className="inline-block rounded-full border border-attention/30 bg-attention-soft px-3 py-1 text-sm font-semibold text-attention">
          {model.demoLabel}
        </p>
        <div className="mt-3 flex items-center gap-3">
          <LogoMark />
          <div>
            <h2 className="font-display text-2xl font-bold text-ink">{model.title}</h2>
            <p className="text-ink-secondary">{model.date}</p>
          </div>
        </div>
      </header>

      <div className="mt-5 space-y-5">
        <div className="space-y-5">
          <p className="text-sm font-semibold uppercase tracking-wide text-ink-secondary">Reported by you</p>
          {reported.map((section) => (
            <Section key={section.id} section={section} />
          ))}
        </div>

        <div className="space-y-5 border-t border-line pt-5">
          <p className="text-sm font-semibold uppercase tracking-wide text-ink-secondary">
            From the assessment · provisional
          </p>
          {fromAssessment.map((section) => (
            <Section key={section.id} section={section} />
          ))}
          {model.serviceText ? (
            <section className="print-avoid-break">
              <h3 className="font-display text-lg font-bold text-ink">Summary text from the assessment service</h3>
              <p className="mt-1.5 whitespace-pre-wrap text-ink">{model.serviceText}</p>
            </section>
          ) : null}
        </div>
      </div>

      <footer className="mt-6 border-t border-line pt-4 text-sm text-ink-secondary">
        <p>{model.disclaimer}</p>
        <p className="mt-1 font-semibold text-attention">{model.demoLabel}</p>
      </footer>
    </article>
  );
}
