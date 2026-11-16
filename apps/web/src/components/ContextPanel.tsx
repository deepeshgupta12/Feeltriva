import { useState } from 'react';

import type { ApiError } from '@/api/errors';
import type { ObservationRecord } from '@/api/types';
import { errorCopy } from '@/lib/errorCopy';
import type { ObservationRevision } from '@/state/AssessmentController';
import { groupObservations } from '@/state/selectors';

import { ObservationChip } from './ObservationChip';
import { ObservationEditor, type ObservationEditorMode } from './ObservationEditor';

interface ContextPanelProps {
  /** Current (non-superseded) observations from the authoritative session. */
  observations: ObservationRecord[];
  busy?: boolean;
  /** Failure of the last confirm/correct request, shown inside the editor. */
  error?: ApiError | null;
  onConfirm: (observationId: string) => Promise<boolean>;
  onRevise: (observationId: string, revision: ObservationRevision) => Promise<boolean>;
  /** Hide the section title when the surrounding sheet or card already shows it. */
  showTitle?: boolean;
  headingLevel?: 'h2' | 'h3';
  /** Omit the interactive actions (used where details are shown for reference only). */
  readOnly?: boolean;
}

export const CONTEXT_PANEL_TITLE = 'What you’ve shared';

interface EditorState {
  observationId: string;
  mode: ObservationEditorMode;
}

/**
 * "What you've shared": the editable record of what the service has saved, grouped as
 * Reported, Not present and Needs clarification. "Not present" only ever lists explicit
 * denials: something the user has not mentioned is unknown and is not shown at all.
 */
export function ContextPanel({
  observations,
  busy = false,
  error = null,
  onConfirm,
  onRevise,
  showTitle = true,
  headingLevel = 'h2',
  readOnly = false,
}: ContextPanelProps) {
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
  const groups = groupObservations(observations);
  const editing = editor ? observations.find((item) => item.observation_id === editor.observationId) : undefined;
  const Heading = headingLevel;
  const SubHeading = headingLevel === 'h2' ? 'h3' : 'h4';

  const handleSave = async (revision: ObservationRevision) => {
    if (!editor) {
      return;
    }
    setSaving(true);
    setSaveFailed(false);
    const accepted = await onRevise(editor.observationId, revision);
    setSaving(false);
    if (accepted) {
      setEditor(null);
    } else {
      setSaveFailed(true);
    }
  };

  const renderGroup = (title: string, description: string, items: ObservationRecord[]) => (
    <section aria-label={title}>
      <SubHeading className="font-display text-base font-bold text-ink">{title}</SubHeading>
      <p className="text-sm text-ink-secondary">{description}</p>
      <ul className="mt-2 space-y-2">
        {items.map((observation) => (
          <ObservationChip
            key={observation.observation_id}
            observation={observation}
            busy={busy}
            onConfirm={readOnly ? undefined : () => void onConfirm(observation.observation_id)}
            onEdit={readOnly ? undefined : () => setEditor({ observationId: observation.observation_id, mode: 'edit' })}
            onCorrect={
              readOnly ? undefined : () => setEditor({ observationId: observation.observation_id, mode: 'correct' })
            }
          />
        ))}
      </ul>
    </section>
  );

  return (
    <div className="space-y-5">
      {showTitle ? <Heading className="font-display text-lg font-bold text-ink">{CONTEXT_PANEL_TITLE}</Heading> : null}

      {observations.length === 0 ? (
        <p className="rounded-control border border-dashed border-line p-4 text-[0.9375rem] text-ink-secondary">
          Nothing saved yet. Details appear here after you describe how you’re feeling, so you can check and correct
          them.
        </p>
      ) : null}

      {groups.reported.length > 0 ? renderGroup('Reported', 'What you’ve told us you have.', groups.reported) : null}
      {groups.notPresent.length > 0
        ? renderGroup('Not present', 'Only what you’ve told us you don’t have.', groups.notPresent)
        : null}
      {groups.needsClarification.length > 0
        ? renderGroup(
            'Needs clarification',
            'Details that are unclear or that you weren’t sure about.',
            groups.needsClarification,
          )
        : null}

      {editor && editing ? (
        <ObservationEditor
          key={`${editor.observationId}:${editor.mode}`}
          observation={editing}
          mode={editor.mode}
          pending={saving}
          error={
            saveFailed ? (error ? errorCopy(error).message : 'That change wasn’t saved. Check it and try again.') : null
          }
          onSave={(revision) => void handleSave(revision)}
          onClose={() => {
            setEditor(null);
            setSaveFailed(false);
          }}
        />
      ) : null}
    </div>
  );
}
