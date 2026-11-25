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
      <ReviewPageHeader
        title={title}
        badge={<StatusBadge tone="neutral">Imported dataset audit · counted from the data files</StatusBadge>}
      >
        {children}
      </ReviewPageHeader>
      {state.status === 'loading' ? <ReviewLoading label="Loading…" /> : null}
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
      title="Repeated columns in the data files"
      caption="Column headings that appear more than once in the symptom table of archive 16"
    >
      <p>
        37 column headings appear more than once in the symptom table of archive 16, and for every one there are rows in
        which the repeated columns disagree. Each column is kept exactly as it came, so that someone can decide which
        one to trust.
      </p>
      <p>
        One row can disagree on several headings, so the numbers of disagreeing rows cannot be added up to a number of
        different rows.
      </p>
    </MappingsView>
  );
}

export function ReviewFeatureMappingsPage() {
  return (
    <MappingsView
      kind="feature"
      title="Symptom and question names"
      caption="A sample of columns of the data files and the names suggested for them"
    >
      <p>
        A sample: one row for each column of a data file, with its heading exactly as it came. The name suggested for it
        is based on its wording only. The columns include questions and past history, not only symptoms, and none has
        been checked by a clinician.
      </p>
    </MappingsView>
  );
}

export function ReviewDiseaseMappingsPage() {
  return (
    <MappingsView
      kind="disease"
      title="Condition names"
      caption="A sample of condition names from the data files and the name each is grouped under"
    >
      <p>
        A sample of condition names from the data files, grouped only when they are spelled the same once capital
        letters and extra spaces are ignored. Being in one group does not mean the names are the same condition, and
        none is clinically approved.
      </p>
    </MappingsView>
  );
}
