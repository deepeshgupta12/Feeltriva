import { ChevronDown, CircleHelp } from 'lucide-react';
import { useId, useMemo, useState, type FormEvent } from 'react';

import { parseAnswerSchema, type AnswerValue, type Question } from '@/api/types';
import { draftFromValue, emptyDraft, resolveDraft, type AnswerDraft } from '@/lib/answers';
import type { UnsentAnswer } from '@/state/AssessmentController';

import { AnswerOptions } from './AnswerOptions';
import { StatusPanel } from './StatusPanel';
import { Button } from './ui/Button';

interface FollowUpQuestionProps {
  question: Question;
  /** A choice made for this same question that the service has not accepted yet. */
  unsentAnswer?: UnsentAnswer | null;
  /** The answer is being sent. Controls are locked and repeat submits are ignored. */
  pending?: boolean;
  /** Any detail-changing request is in flight. */
  busy?: boolean;
  /** Message from the service when the answer was rejected (for example a 422). */
  serverError?: string | null;
  onSubmit: (value: AnswerValue, label: string) => void;
}

/**
 * Shows exactly one follow-up question. The answer is sent only when the user presses
 * "Send answer"; selecting an option never submits on its own. The "Why this question?"
 * disclosure shows backend-provided text and is hidden when there is none.
 */
export function FollowUpQuestion({
  question,
  unsentAnswer = null,
  pending = false,
  busy = false,
  serverError = null,
  onSubmit,
}: FollowUpQuestionProps) {
  const id = useId();
  const schema = useMemo(() => parseAnswerSchema(question.answer_schema), [question.answer_schema]);
  const restored = unsentAnswer && unsentAnswer.questionId === question.question_id ? unsentAnswer : null;

  const [draft, setDraft] = useState<AnswerDraft | null>(() => {
    if (!schema) return null;
    return restored ? draftFromValue(schema, restored.value) : emptyDraft(schema);
  });
  const [validationError, setValidationError] = useState<string | null>(null);

  if (!schema || !draft) {
    return (
      <StatusPanel tone="attention" title="This question can’t be shown here" headingLevel="h3">
        <p>
          This version of the app doesn’t support the type of answer this question needs. You can still add details in
          your own words below.
        </p>
      </StatusPanel>
    );
  }

  const error = validationError ?? serverError;
  const locked = pending || busy;

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (locked) {
      return;
    }
    const result = resolveDraft(schema, draft);
    if (!result.ok) {
      setValidationError(result.message);
      return;
    }
    setValidationError(null);
    onSubmit(result.value, result.label);
  };

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="rounded-card border border-line bg-surface p-5 sm:p-6"
      aria-labelledby={`${id}-wording`}
    >
      <p className="text-sm font-semibold uppercase tracking-wide text-ink-secondary">Follow-up question</p>
      <h2 id={`${id}-wording`} className="mt-1.5 font-display text-xl font-bold text-ink">
        {question.wording}
      </h2>

      {restored ? (
        <p className="mt-3 rounded-control border border-attention/30 bg-attention-soft px-3.5 py-2.5 text-[0.9375rem] text-attention">
          Your answer wasn’t sent. Check it still applies, then send it again.
        </p>
      ) : null}

      <div className="mt-4">
        <AnswerOptions
          schema={schema}
          draft={draft}
          onDraftChange={(next) => {
            setDraft(next);
            setValidationError(null);
          }}
          groupLabelId={`${id}-wording`}
          disabled={locked}
          errorId={`${id}-error`}
          invalid={error !== null}
        />
      </div>

      {error ? (
        <p id={`${id}-error`} role="alert" className="mt-3 text-[0.9375rem] font-medium text-urgent">
          {error}
        </p>
      ) : null}

      {schema.help_text ? (
        <details className="group mt-4 rounded-control border border-line">
          <summary className="flex min-h-11 list-none items-center gap-2 rounded-control px-3.5 font-medium text-ink-secondary hover:text-ink [&::-webkit-details-marker]:hidden">
            <CircleHelp aria-hidden="true" className="size-4 shrink-0" />
            Why this question?
            <ChevronDown
              aria-hidden="true"
              className="ml-auto size-4 shrink-0 transition-transform duration-150 group-open:rotate-180"
            />
          </summary>
          <p className="px-3.5 pb-3 text-[0.9375rem] text-ink-secondary">{schema.help_text}</p>
        </details>
      ) : null}

      <div className="mt-5">
        <Button type="submit" loading={pending} loadingLabel="Sending your answer…" disabled={busy && !pending}>
          Send answer
        </Button>
      </div>
    </form>
  );
}
