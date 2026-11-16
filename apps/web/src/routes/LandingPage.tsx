import {
  ArrowRight,
  ClipboardList,
  FileText,
  ListChecks,
  MessageCircle,
  MessagesSquare,
  Route as RouteIcon,
} from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router';

import type { ObservationRecord } from '@/api/types';
import { MessageCard } from '@/components/MessageCard';
import { ObservationChip } from '@/components/ObservationChip';
import { ObservationEditor, type ObservationEditorMode } from '@/components/ObservationEditor';
import { ButtonLink } from '@/components/ui/Button';
import { LINK_CLASSES } from '@/components/ui/buttonStyles';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { INTENDED_USE_STATEMENT } from '@/components/UncertaintyPanel';
import { usePageMeta } from '@/state/hooks';

/** Static illustration for the hero card. It is not produced by, or sent to, any service. */
const EXAMPLE_INPUT = 'I’ve had a headache since yesterday and I feel more tired than usual.';
const EXAMPLE_OBSERVATION: ObservationRecord = {
  observation_id: 'example-observation',
  observation_version: 1,
  feature_id: 'example.headache',
  raw_phrase: 'Headache',
  presence: 'present',
  onset: 'Since yesterday',
  confirmed: false,
};

const GROUP_LABEL = {
  present: 'Reported',
  absent: 'Not present',
  uncertain: 'Needs clarification',
  not_asked: 'Reported',
} as const;

function ExampleConversation() {
  const [observation, setObservation] = useState<ObservationRecord>(EXAMPLE_OBSERVATION);
  const [editor, setEditor] = useState<ObservationEditorMode | null>(null);

  return (
    <section
      aria-labelledby="example-heading"
      className="rounded-card border border-line bg-surface p-5 shadow-float sm:p-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="example-heading" className="font-display text-lg font-bold text-ink">
          Example conversation
        </h2>
        <StatusBadge tone="sample">Illustration only</StatusBadge>
      </div>
      <ul className="mt-4 space-y-3">
        <MessageCard author="assistant">What have you been feeling?</MessageCard>
        <MessageCard author="user">{EXAMPLE_INPUT}</MessageCard>
      </ul>
      <div className="mt-4 rounded-control bg-page p-3">
        <p className="text-sm font-semibold text-ink-secondary">
          What you’ve shared · {GROUP_LABEL[observation.presence]}
        </p>
        <ul className="mt-2">
          <ObservationChip
            observation={observation}
            onConfirm={() => setObservation({ ...observation, confirmed: true })}
            onEdit={() => setEditor('edit')}
            onCorrect={() => setEditor('correct')}
          />
        </ul>
        <p className="mt-2 text-sm text-ink-secondary">
          You stay in control: confirm, edit or correct anything we understood.
        </p>
      </div>
      {editor ? (
        <ObservationEditor
          key={editor}
          observation={observation}
          mode={editor}
          onClose={() => setEditor(null)}
          onSave={(revision) => {
            setObservation({
              ...observation,
              presence: revision.presence,
              onset: revision.onset?.trim() || undefined,
              duration: revision.duration?.trim() || undefined,
              severity: revision.severity?.trim() || undefined,
              confirmed: true,
            });
            setEditor(null);
          }}
        />
      ) : null}
    </section>
  );
}

function Step({
  number,
  title,
  children,
  icon,
}: {
  number: number;
  title: string;
  children: ReactNode;
  icon: ReactNode;
}) {
  return (
    <li className="rounded-card border border-line bg-surface p-5 sm:p-6">
      <div className="flex items-center gap-3">
        <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-teal-soft text-primary">
          {icon}
        </span>
        <p className="text-sm font-semibold uppercase tracking-wide text-ink-secondary">Step {number}</p>
      </div>
      <h3 className="mt-3 font-display text-xl font-bold text-ink">{title}</h3>
      <p className="mt-1.5 text-ink-secondary">{children}</p>
    </li>
  );
}

export function LandingPage() {
  usePageMeta('Understand your symptoms. Know your next step.');
  const { hash } = useLocation();

  // In-page links ("How it works", "About your data") arrive as a hash on this route.
  useEffect(() => {
    if (!hash) {
      return;
    }
    const target = document.getElementById(hash.slice(1));
    if (target) {
      target.scrollIntoView?.({ block: 'start' });
      target.focus({ preventScroll: true });
    }
  }, [hash]);

  return (
    <div>
      <section className="mx-auto grid max-w-[1200px] items-center gap-8 px-4 py-10 sm:px-6 sm:py-14 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:gap-12 lg:py-20">
        <div>
          <p className="font-semibold text-primary">Understand your symptoms. Know your next step.</p>
          <h1
            tabIndex={-1}
            className="mt-3 font-display text-[2.25rem] font-bold leading-[1.1] tracking-tight text-ink sm:text-[2.5rem] lg:text-[3.375rem]"
          >
            Tell us how you’re feeling.
          </h1>
          <p className="mt-4 max-w-xl text-lg text-ink-secondary">
            Organize your symptoms, answer useful questions and prepare for the next step.
          </p>
          <div className="mt-7 flex flex-col gap-3 sm:flex-row sm:items-center">
            <ButtonLink to="/start" icon={<MessageCircle aria-hidden="true" className="size-5 shrink-0" />}>
              Try a sample assessment
            </ButtonLink>
            <Link
              to={{ pathname: '/', hash: '#how-it-works' }}
              className={`inline-flex min-h-11 items-center gap-1.5 px-2 ${LINK_CLASSES}`}
            >
              See how it works
              <ArrowRight aria-hidden="true" className="size-4 shrink-0" />
            </Link>
          </div>
          <p className="mt-5 max-w-xl text-[0.9375rem] text-ink-secondary">
            This is a design demo with sample scenarios. Please try the sample rather than entering private health
            information into a shared preview.
          </p>
        </div>
        <ExampleConversation />
      </section>

      <section
        id="how-it-works"
        tabIndex={-1}
        aria-labelledby="how-heading"
        className="scroll-mt-24 border-y border-line bg-surface/60"
      >
        <div className="mx-auto max-w-[1200px] px-4 py-12 sm:px-6">
          <h2 id="how-heading" className="font-display text-[1.75rem] font-bold text-ink">
            How it works
          </h2>
          <ol className="mt-6 grid gap-4 md:grid-cols-3">
            <Step
              number={1}
              title="Describe what you feel"
              icon={<MessagesSquare aria-hidden="true" className="size-5" />}
            >
              Write in your own words. You’ll see what was understood and can correct it.
            </Step>
            <Step
              number={2}
              title="Clarify the important details"
              icon={<ListChecks aria-hidden="true" className="size-5" />}
            >
              Answer one follow-up question at a time. “I’m not sure” is always an acceptable answer when offered.
            </Step>
            <Step number={3} title="Review your next step" icon={<RouteIcon aria-hidden="true" className="size-5" />}>
              See a provisional next step, what is still uncertain, and a summary you can take to a consultation.
            </Step>
          </ol>
        </div>
      </section>

      <section aria-labelledby="output-heading" className="mx-auto max-w-[1200px] px-4 py-12 sm:px-6">
        <h2 id="output-heading" className="font-display text-[1.75rem] font-bold text-ink">
          What you get
        </h2>
        <ul className="mt-6 grid gap-4 md:grid-cols-3">
          <li className="rounded-card border border-line bg-surface p-5 sm:p-6">
            <ClipboardList aria-hidden="true" className="size-6 text-primary" />
            <h3 className="mt-3 font-display text-lg font-bold text-ink">A symptom summary</h3>
            <p className="mt-1.5 text-ink-secondary">
              What you reported, what you said you don’t have, and when things started.
            </p>
          </li>
          <li className="rounded-card border border-line bg-surface p-5 sm:p-6">
            <ListChecks aria-hidden="true" className="size-6 text-primary" />
            <h3 className="mt-3 font-display text-lg font-bold text-ink">Provisional explanations, when supported</h3>
            <p className="mt-1.5 text-ink-secondary">
              Possible explanations are shown only when there is supporting information, and never as a confirmed
              diagnosis.
            </p>
          </li>
          <li className="rounded-card border border-line bg-surface p-5 sm:p-6">
            <FileText aria-hidden="true" className="size-6 text-primary" />
            <h3 className="mt-3 font-display text-lg font-bold text-ink">Consultation-ready notes</h3>
            <p className="mt-1.5 text-ink-secondary">
              A clear summary you review first, then print or copy if you choose to.
            </p>
          </li>
        </ul>
        <p className="mt-6 max-w-3xl rounded-card border border-info/25 bg-info-soft p-5 text-info">
          {INTENDED_USE_STATEMENT}
        </p>
      </section>

      <section
        id="your-data"
        tabIndex={-1}
        aria-labelledby="data-heading"
        className="scroll-mt-24 border-t border-line bg-surface/60"
      >
        <div className="mx-auto max-w-[1200px] px-4 py-12 sm:px-6">
          <h2 id="data-heading" className="font-display text-[1.75rem] font-bold text-ink">
            About your data
          </h2>
          <ul className="mt-4 max-w-3xl list-disc space-y-2 pl-5 text-ink-secondary">
            <li>This demo keeps sample sessions in your browser’s memory only. Reloading the page clears them.</li>
            <li>No account is created, and health details are not written to browser storage.</li>
            <li>Nothing is emailed or shared automatically. You choose whether to print or copy a summary.</li>
            <li>Using your information to improve the service is a separate choice that is off by default.</li>
          </ul>
          <p className="mt-4">
            <Link to="/settings/privacy" className={LINK_CLASSES}>
              Privacy settings and details
            </Link>
          </p>
        </div>
      </section>
    </div>
  );
}
