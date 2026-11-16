import type { ReactNode } from 'react';

import type { MappingKind, MappingRow } from '@/api/reviewService';
import { ReviewTable } from '@/components/review/ReviewTable';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useAsync } from '@/lib/useAsync';
import { useServices } from '@/state/services';

import { ReviewLoadError, ReviewLoading, ReviewPageHeader } from './ReviewPageHeader';

interface MappingsViewProps {
  kind: MappingKind;
  title: string;
  caption: string;
  children: ReactNode;
}

function MappingsView({ kind, title, caption, children }: MappingsViewProps) {
  const { review } = useServices();
  const { state, reload, setData } = useAsync(`review:mappings:${kind}`, () => review.listMappings(kind));

  const replaceRow = (rows: MappingRow[], updated: MappingRow) =>
    rows.map((row) => (row.id === updated.id ? updated : row));

  return (
    <div>
      <ReviewPageHeader title={title} badge={<StatusBadge tone="neutral">Imported dataset audit</StatusBadge>}>
        {children}
      </ReviewPageHeader>
      {state.status === 'loading' ? <ReviewLoading label="Loading mappings…" /> : null}
      {state.status === 'failed' ? <ReviewLoadError onRetry={reload} /> : null}
      {state.status === 'loaded' ? (
        <ReviewTable
          caption={caption}
          rows={state.data}
          onSaveNote={async (rowId, text) => {
            setData(replaceRow(state.data, await review.saveNote(rowId, text)));
          }}
          onSetStatus={async (rowId, status) => {
            setData(replaceRow(state.data, await review.setStatus(rowId, status)));
          }}
        />
      ) : null}
    </div>
  );
}

export function ReviewDataQualityPage() {
  return (
    <MappingsView
      kind="data_quality"
      title="Data quality"
      caption="Repeated header names in the archive 16 symptom matrix"
    >
      <p>
        37 header names appear more than once in the archive 16 symptom matrix, and every one has rows where its columns
        disagree. Each column position is kept as imported so the columns can be reconciled by a reviewer.
      </p>
      <p>
        A single row can disagree on several headers, so the conflicting-row counts cannot be added together as a count
        of unique rows.
      </p>
    </MappingsView>
  );
}

export function ReviewFeatureMappingsPage() {
  return (
    <MappingsView
      kind="feature"
      title="Feature mappings"
      caption="Sample of positional feature mappings by source column"
    >
      <p>
        A sample of the positional feature mappings: one row per source column, with the header exactly as imported. The
        proposed terms are lexical candidates. They include questionnaire and history items and are not verified
        symptoms.
      </p>
    </MappingsView>
  );
}

export function ReviewDiseaseMappingsPage() {
  return (
    <MappingsView
      kind="disease"
      title="Disease mappings"
      caption="Sample of lexical disease label mappings by source file"
    >
      <p>
        A sample of source labels grouped by lexical normalisation only. Sharing a group means the labels have the same
        spelling after normalisation; it does not mean they are the same condition or that any is clinically approved.
      </p>
    </MappingsView>
  );
}
