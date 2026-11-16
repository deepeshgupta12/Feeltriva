import { useId } from 'react';

import type { AnswerSchema, DurationUnit } from '@/api/types';
import { choiceOptions, durationUnits, NOT_SURE_LABEL, numberUnits, type AnswerDraft } from '@/lib/answers';
import { cn } from '@/lib/cn';

interface AnswerOptionsProps {
  schema: AnswerSchema;
  draft: AnswerDraft;
  onDraftChange: (draft: AnswerDraft) => void;
  /** Accessible name for the group (the question wording). */
  groupLabelId: string;
  disabled?: boolean;
  errorId?: string;
  invalid?: boolean;
}

const OPTION_ROW =
  'flex min-h-12 cursor-pointer items-center gap-3 rounded-control border px-3.5 py-2.5 transition-colors duration-150';

function optionRowClasses(selected: boolean, disabled: boolean): string {
  return cn(
    OPTION_ROW,
    selected ? 'border-primary bg-teal-soft' : 'border-line bg-surface hover:border-ink-muted',
    disabled && 'cursor-not-allowed opacity-60',
  );
}

const CONTROL = 'size-5 shrink-0 accent-primary';

/**
 * Renders the input for one backend-provided answer schema: yes / no / not sure, single
 * choice, multiple choice, number with unit, duration, or free text. Nothing is
 * preselected, and "I'm not sure" appears only when the schema allows it.
 */
export function AnswerOptions({
  schema,
  draft,
  onDraftChange,
  groupLabelId,
  disabled = false,
  errorId,
  invalid = false,
}: AnswerOptionsProps) {
  const id = useId();
  const describedBy = invalid && errorId ? errorId : undefined;
  const notSureAllowed = schema.allow_not_sure === true;

  if (draft.kind === 'choice') {
    return (
      <div
        role="radiogroup"
        aria-labelledby={groupLabelId}
        aria-describedby={describedBy}
        aria-invalid={invalid || undefined}
        className="space-y-2"
      >
        {choiceOptions(schema).map((option) => {
          const selected = draft.value === option.value;
          return (
            <label key={option.value} className={optionRowClasses(selected, disabled)}>
              <input
                type="radio"
                name={`${id}-choice`}
                value={option.value}
                checked={selected}
                disabled={disabled}
                onChange={() => onDraftChange({ kind: 'choice', value: option.value })}
                className={CONTROL}
              />
              <span className="font-medium text-ink">{option.label}</span>
            </label>
          );
        })}
      </div>
    );
  }

  if (draft.kind === 'multi') {
    const toggle = (value: string) => {
      const values = draft.values.includes(value)
        ? draft.values.filter((item) => item !== value)
        : [...draft.values, value];
      onDraftChange({ kind: 'multi', values, notSure: false });
    };
    return (
      <div role="group" aria-labelledby={groupLabelId} aria-describedby={describedBy} className="space-y-2">
        <p className="text-sm text-ink-secondary">Select all that apply.</p>
        {(schema.options ?? []).map((option) => {
          const selected = draft.values.includes(option.value);
          return (
            <label key={option.value} className={optionRowClasses(selected, disabled)}>
              <input
                type="checkbox"
                checked={selected}
                disabled={disabled}
                onChange={() => toggle(option.value)}
                className={CONTROL}
              />
              <span className="font-medium text-ink">{option.label}</span>
            </label>
          );
        })}
        {notSureAllowed ? (
          <label className={optionRowClasses(draft.notSure, disabled)}>
            <input
              type="checkbox"
              checked={draft.notSure}
              disabled={disabled}
              onChange={(event) => onDraftChange({ kind: 'multi', values: [], notSure: event.target.checked })}
              className={CONTROL}
            />
            <span className="font-medium text-ink">{NOT_SURE_LABEL}</span>
          </label>
        ) : null}
      </div>
    );
  }

  const notSureToggle = (checked: boolean, onToggle: (next: boolean) => void) =>
    notSureAllowed ? (
      <label className={cn(optionRowClasses(checked, disabled), 'mt-2')}>
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onToggle(event.target.checked)}
          className={CONTROL}
        />
        <span className="font-medium text-ink">{NOT_SURE_LABEL}</span>
      </label>
    ) : null;

  if (draft.kind === 'number') {
    const units = numberUnits(schema);
    const inactive = disabled || draft.notSure;
    return (
      <div role="group" aria-labelledby={groupLabelId} aria-describedby={describedBy}>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[8rem] flex-1">
            <label htmlFor={`${id}-number`} className="mb-1 block text-sm font-medium text-ink-secondary">
              Number
            </label>
            <input
              id={`${id}-number`}
              type="text"
              inputMode="decimal"
              autoComplete="off"
              value={draft.text}
              disabled={inactive}
              aria-invalid={invalid || undefined}
              aria-describedby={describedBy}
              onChange={(event) => onDraftChange({ ...draft, text: event.target.value })}
              className="field-control"
            />
          </div>
          {units.length > 1 ? (
            <div className="min-w-[9rem] flex-1">
              <label htmlFor={`${id}-unit`} className="mb-1 block text-sm font-medium text-ink-secondary">
                Unit
              </label>
              <select
                id={`${id}-unit`}
                value={draft.unit}
                disabled={inactive}
                onChange={(event) => onDraftChange({ ...draft, unit: event.target.value })}
                className="field-control"
              >
                <option value="">Choose a unit</option>
                {units.map((unit) => (
                  <option key={unit} value={unit}>
                    {unit}
                  </option>
                ))}
              </select>
            </div>
          ) : units.length === 1 ? (
            <p className="flex min-h-12 items-center font-medium text-ink-secondary">{units[0]}</p>
          ) : null}
        </div>
        {notSureToggle(draft.notSure, (next) => onDraftChange({ ...draft, notSure: next }))}
      </div>
    );
  }

  if (draft.kind === 'duration') {
    const inactive = disabled || draft.notSure;
    return (
      <div role="group" aria-labelledby={groupLabelId} aria-describedby={describedBy}>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[8rem] flex-1">
            <label htmlFor={`${id}-duration`} className="mb-1 block text-sm font-medium text-ink-secondary">
              How long
            </label>
            <input
              id={`${id}-duration`}
              type="text"
              inputMode="decimal"
              autoComplete="off"
              value={draft.text}
              disabled={inactive}
              aria-invalid={invalid || undefined}
              aria-describedby={describedBy}
              onChange={(event) => onDraftChange({ ...draft, text: event.target.value })}
              className="field-control"
            />
          </div>
          <div className="min-w-[9rem] flex-1">
            <label htmlFor={`${id}-duration-unit`} className="mb-1 block text-sm font-medium text-ink-secondary">
              Unit of time
            </label>
            <select
              id={`${id}-duration-unit`}
              value={draft.unit}
              disabled={inactive}
              onChange={(event) => onDraftChange({ ...draft, unit: event.target.value as DurationUnit | '' })}
              className="field-control"
            >
              <option value="">Choose a unit</option>
              {durationUnits(schema).map((unit) => (
                <option key={unit} value={unit}>
                  {unit.charAt(0).toUpperCase() + unit.slice(1)}
                </option>
              ))}
            </select>
          </div>
        </div>
        {notSureToggle(draft.notSure, (next) => onDraftChange({ ...draft, notSure: next }))}
      </div>
    );
  }

  return (
    <div>
      <textarea
        rows={3}
        value={draft.text}
        disabled={disabled || draft.notSure}
        aria-labelledby={groupLabelId}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        onChange={(event) => onDraftChange({ ...draft, text: event.target.value })}
        className="field-control min-h-24 resize-y"
      />
      {notSureToggle(draft.notSure, (next) => onDraftChange({ ...draft, notSure: next }))}
    </div>
  );
}
