import { useId, useState, type FormEvent } from 'react';

import type { ObservationRecord, Presence } from '@/api/types';
import type { ObservationRevision } from '@/state/AssessmentController';
import { observationLabel } from '@/state/selectors';

import { Button } from './ui/Button';
import { Dialog } from './ui/Dialog';

export type ObservationEditorMode = 'edit' | 'correct';

interface ObservationEditorProps {
  observation: ObservationRecord;
  mode: ObservationEditorMode;
  pending?: boolean;
  error?: string | null;
  onSave: (revision: ObservationRevision) => void;
  onClose: () => void;
}

type EditablePresence = Exclude<Presence, 'not_asked'>;

const PRESENCE_OPTIONS: ReadonlyArray<{ value: EditablePresence; label: string; hint: string }> = [
  { value: 'present', label: 'I have this', hint: 'Listed under “Reported”.' },
  { value: 'absent', label: 'I don’t have this', hint: 'Listed under “Not present”.' },
  { value: 'uncertain', label: 'I’m not sure', hint: 'Listed under “Needs clarification”.' },
];

/**
 * Corrects one shared detail. Corrections are sent as a new revision that supersedes the
 * old one; nothing is silently deleted, and any earlier result stops being current.
 *
 * "Edit" changes presence and timing details. "Remove/correct" asks what is true instead,
 * with no option preselected.
 */
export function ObservationEditor({
  observation,
  mode,
  pending = false,
  error = null,
  onSave,
  onClose,
}: ObservationEditorProps) {
  const id = useId();
  const label = observationLabel(observation);
  const initialPresence: EditablePresence | null =
    mode === 'edit' && observation.presence !== 'not_asked' ? observation.presence : null;

  const [presence, setPresence] = useState<EditablePresence | null>(initialPresence);
  const [onset, setOnset] = useState(observation.onset ?? '');
  const [duration, setDuration] = useState(observation.duration ?? '');
  const [severity, setSeverity] = useState(observation.severity ?? '');
  const [validationError, setValidationError] = useState<string | null>(null);

  const options =
    mode === 'correct' ? PRESENCE_OPTIONS.filter((option) => option.value !== 'present') : PRESENCE_OPTIONS;
  const showDetails = mode === 'edit' && presence === 'present';
  const message = validationError ?? error;

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (pending) {
      return;
    }
    if (presence === null) {
      setValidationError('Choose an option to continue.');
      return;
    }
    setValidationError(null);
    onSave(showDetails ? { presence, onset, duration, severity } : { presence });
  };

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !pending) onClose();
      }}
      title={mode === 'edit' ? 'Edit this detail' : 'Remove or correct this detail'}
      description={`“${label}”`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" form={`${id}-form`} loading={pending} loadingLabel="Saving…">
            Save change
          </Button>
        </>
      }
    >
      <form id={`${id}-form`} onSubmit={handleSubmit} noValidate className="space-y-5">
        <fieldset>
          <legend className="font-semibold text-ink">
            {mode === 'edit' ? 'Which is true for you?' : 'What should we record instead?'}
          </legend>
          <div className="mt-2 space-y-2" role="radiogroup" aria-describedby={message ? `${id}-error` : undefined}>
            {options.map((option) => (
              <label
                key={option.value}
                className={`flex min-h-12 cursor-pointer items-start gap-3 rounded-control border px-3.5 py-2.5 ${
                  presence === option.value ? 'border-primary bg-teal-soft' : 'border-line hover:border-ink-muted'
                }`}
              >
                <input
                  type="radio"
                  name={`${id}-presence`}
                  value={option.value}
                  checked={presence === option.value}
                  disabled={pending}
                  onChange={() => {
                    setPresence(option.value);
                    setValidationError(null);
                  }}
                  className="mt-1 size-5 shrink-0 accent-primary"
                />
                <span>
                  <span className="block font-medium text-ink">{option.label}</span>
                  <span className="block text-sm text-ink-secondary">{option.hint}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        {showDetails ? (
          <div className="space-y-4">
            <div>
              <label htmlFor={`${id}-onset`} className="mb-1 block font-medium text-ink">
                When it started <span className="font-normal text-ink-secondary">(optional)</span>
              </label>
              <input
                id={`${id}-onset`}
                type="text"
                value={onset}
                maxLength={200}
                disabled={pending}
                onChange={(event) => setOnset(event.target.value)}
                className="field-control"
              />
            </div>
            <div>
              <label htmlFor={`${id}-duration`} className="mb-1 block font-medium text-ink">
                How long it lasts <span className="font-normal text-ink-secondary">(optional)</span>
              </label>
              <input
                id={`${id}-duration`}
                type="text"
                value={duration}
                maxLength={200}
                disabled={pending}
                onChange={(event) => setDuration(event.target.value)}
                className="field-control"
              />
            </div>
            <div>
              <label htmlFor={`${id}-severity`} className="mb-1 block font-medium text-ink">
                How much it affects you <span className="font-normal text-ink-secondary">(optional)</span>
              </label>
              <input
                id={`${id}-severity`}
                type="text"
                value={severity}
                maxLength={200}
                disabled={pending}
                onChange={(event) => setSeverity(event.target.value)}
                className="field-control"
              />
            </div>
          </div>
        ) : null}

        <p className="text-[0.9375rem] text-ink-secondary">
          Saving a change means any earlier result no longer applies and will need updating.
        </p>

        {message ? (
          <p id={`${id}-error`} role="alert" className="text-[0.9375rem] font-medium text-urgent">
            {message}
          </p>
        ) : null}
      </form>
    </Dialog>
  );
}
