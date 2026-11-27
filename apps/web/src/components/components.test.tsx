import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { ObservationRecord, Question } from '@/api/types';

import { FollowUpQuestion } from './FollowUpQuestion';
import { ObservationChip } from './ObservationChip';
import { SourceList } from './SourceList';

function question(answer_schema: unknown): Question {
  return { question_id: 'q.test', wording: 'Sample question wording?', answer_schema, observation_version: 3 };
}

describe('FollowUpQuestion', () => {
  it('preselects nothing and sends only on explicit submit', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<FollowUpQuestion question={question({ type: 'yes_no_unsure' })} onSubmit={onSubmit} />);

    const radios = screen.getAllByRole('radio');
    expect(radios.map((radio) => (radio as HTMLInputElement).value)).toEqual(['yes', 'no', 'not_sure']);
    for (const radio of radios) {
      expect(radio).not.toBeChecked();
    }

    await user.click(screen.getByRole('button', { name: 'Send answer' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Choose an answer to continue.');
    expect(onSubmit).not.toHaveBeenCalled();

    // Choosing an option does not submit by itself.
    await user.click(screen.getByRole('radio', { name: 'No' }));
    expect(onSubmit).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Send answer' }));
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith('no', 'No');
  });

  it('shows "Why this question?" only when the backend supplied help text', () => {
    const { unmount } = render(
      <FollowUpQuestion
        question={question({ type: 'yes_no_unsure', help_text: 'Backend supplied reason.' })}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByText('Why this question?')).toBeInTheDocument();
    expect(screen.getByText('Backend supplied reason.')).toBeInTheDocument();
    unmount();

    render(<FollowUpQuestion question={question({ type: 'yes_no_unsure' })} onSubmit={vi.fn()} />);
    expect(screen.queryByText('Why this question?')).not.toBeInTheDocument();
  });

  it('offers "I’m not sure" for a choice only when the schema allows it', () => {
    const options = [
      { value: 'a', label: 'Option A' },
      { value: 'b', label: 'Option B' },
    ];
    const { unmount } = render(
      <FollowUpQuestion question={question({ type: 'single_choice', options })} onSubmit={vi.fn()} />,
    );
    expect(screen.queryByRole('radio', { name: 'I’m not sure' })).not.toBeInTheDocument();
    unmount();

    render(
      <FollowUpQuestion
        question={question({ type: 'single_choice', options, allow_not_sure: true })}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByRole('radio', { name: 'I’m not sure' })).toBeInTheDocument();
  });

  it('sends the agreed payloads for multiple choice, number, duration and free text', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const options = [
      { value: 'a', label: 'Option A' },
      { value: 'b', label: 'Option B' },
    ];

    const multi = render(
      <FollowUpQuestion question={question({ type: 'multiple_choice', options })} onSubmit={onSubmit} />,
    );
    await user.click(screen.getByRole('checkbox', { name: 'Option B' }));
    await user.click(screen.getByRole('checkbox', { name: 'Option A' }));
    await user.click(screen.getByRole('button', { name: 'Send answer' }));
    expect(onSubmit).toHaveBeenLastCalledWith(['a', 'b'], 'Option A, Option B');
    multi.unmount();

    const number = render(
      <FollowUpQuestion
        question={question({ type: 'number', units: ['kg', 'lb'], min: 1, max: 300 })}
        onSubmit={onSubmit}
      />,
    );
    await user.type(screen.getByLabelText('Number'), '70');
    await user.click(screen.getByRole('button', { name: 'Send answer' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a unit.');
    await user.selectOptions(screen.getByLabelText('Unit'), 'kg');
    await user.click(screen.getByRole('button', { name: 'Send answer' }));
    expect(onSubmit).toHaveBeenLastCalledWith({ value: 70, unit: 'kg' }, '70 kg');
    number.unmount();

    const duration = render(<FollowUpQuestion question={question({ type: 'duration' })} onSubmit={onSubmit} />);
    expect(screen.getByLabelText('Unit of time')).toHaveValue('');
    await user.type(screen.getByRole('textbox', { name: 'How long' }), '2');
    await user.selectOptions(screen.getByLabelText('Unit of time'), 'weeks');
    await user.click(screen.getByRole('button', { name: 'Send answer' }));
    expect(onSubmit).toHaveBeenLastCalledWith({ value: 2, unit: 'weeks' }, '2 weeks');
    duration.unmount();

    render(<FollowUpQuestion question={question({ type: 'free_text' })} onSubmit={onSubmit} />);
    await user.type(screen.getByRole('textbox'), 'some words');
    await user.click(screen.getByRole('button', { name: 'Send answer' }));
    expect(onSubmit).toHaveBeenLastCalledWith('some words', 'some words');
  });

  it('restores an unsent answer for the same question and says it must be sent again', () => {
    render(
      <FollowUpQuestion
        question={question({ type: 'yes_no_unsure' })}
        unsentAnswer={{ questionId: 'q.test', value: 'yes', label: 'Yes' }}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByRole('radio', { name: 'Yes' })).toBeChecked();
    expect(
      screen.getByText('Your answer wasn’t sent. Check it still applies, then send it again.'),
    ).toBeInTheDocument();
  });

  it('never attaches an unsent answer from a different question', () => {
    render(
      <FollowUpQuestion
        question={question({ type: 'yes_no_unsure' })}
        unsentAnswer={{ questionId: 'q.other', value: 'yes', label: 'Yes' }}
        onSubmit={vi.fn()}
      />,
    );
    for (const radio of screen.getAllByRole('radio')) {
      expect(radio).not.toBeChecked();
    }
  });

  it('blocks repeat submits while an answer is pending', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <FollowUpQuestion
        question={question({ type: 'yes_no_unsure' })}
        unsentAnswer={{ questionId: 'q.test', value: 'yes', label: 'Yes' }}
        pending
        onSubmit={onSubmit}
      />,
    );
    const button = screen.getByRole('button', { name: 'Sending your answer…' });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('refuses to guess when the answer schema is not one it understands', () => {
    render(<FollowUpQuestion question={question({ type: 'slider', min: 0, max: 10 })} onSubmit={vi.fn()} />);
    expect(screen.getByRole('heading', { name: 'This question can’t be shown here' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send answer' })).not.toBeInTheDocument();
  });

  it('takes a date with a date field, within the bounds of the question, and sends it as a date', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(true);
    render(
      <FollowUpQuestion
        question={question({ type: 'date', earliest: '2026-01-01', latest: '2026-01-31', allow_not_sure: true })}
        onSubmit={onSubmit}
      />,
    );
    const field = screen.getByLabelText('Date');
    expect(field).toHaveAttribute('type', 'date');
    expect(field).toHaveAttribute('min', '2026-01-01');
    expect(field).toHaveAttribute('max', '2026-01-31');
    expect(field).toHaveValue('');
    // Nothing chosen: the form asks for a date and sends nothing.
    await user.click(screen.getByRole('button', { name: 'Send answer' }));
    expect(screen.getByText('Choose a date to continue.')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.change(field, { target: { value: '2026-02-01' } });
    await user.click(screen.getByRole('button', { name: 'Send answer' }));
    expect(screen.getByText('Choose a date on or before 31 January 2026.')).toBeInTheDocument();
    fireEvent.change(field, { target: { value: '2026-01-15' } });
    await user.click(screen.getByRole('button', { name: 'Send answer' }));
    expect(onSubmit).toHaveBeenCalledWith({ date: '2026-01-15' }, '15 January 2026');
  });

  it('lets a person decline a question about clinically relevant context', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(true);
    render(
      <FollowUpQuestion
        question={question({ type: 'yes_no_unsure', allow_prefer_not_to_answer: true })}
        onSubmit={onSubmit}
      />,
    );
    const declined = screen.getByRole('radio', { name: 'Prefer not to answer' });
    expect(declined).not.toBeChecked();
    await user.click(declined);
    await user.click(screen.getByRole('button', { name: 'Send answer' }));
    expect(onSubmit).toHaveBeenCalledWith('prefer_not_to_answer', 'Prefer not to answer');
  });

  it('sends "not sure" as the same one value for a date and for several choices', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(true);
    const dated = render(
      <FollowUpQuestion question={question({ type: 'date', allow_not_sure: true })} onSubmit={onSubmit} />,
    );
    await user.click(screen.getByRole('checkbox', { name: 'I’m not sure' }));
    expect(screen.getByLabelText('Date')).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Send answer' }));
    expect(onSubmit).toHaveBeenLastCalledWith('not_sure', 'I’m not sure');
    dated.unmount();
    render(
      <FollowUpQuestion
        question={question({
          type: 'multiple_choice',
          options: [{ value: 'a', label: 'Option A' }],
          allow_not_sure: true,
        })}
        onSubmit={onSubmit}
      />,
    );
    await user.click(screen.getByRole('checkbox', { name: 'I’m not sure' }));
    await user.click(screen.getByRole('button', { name: 'Send answer' }));
    expect(onSubmit).toHaveBeenLastCalledWith('not_sure', 'I’m not sure');
  });
});

describe('ObservationChip', () => {
  const base: ObservationRecord = {
    observation_id: 'o1',
    observation_version: 1,
    feature_id: 'fx.signal_alpha',
    presence: 'present',
    confirmed: false,
    onset: 'Since yesterday',
  };

  it('asks for confirmation of an unconfirmed interpretation and falls back to a humanised feature id', () => {
    render(
      <ul>
        <ObservationChip observation={base} onConfirm={vi.fn()} onEdit={vi.fn()} onCorrect={vi.fn()} />
      </ul>,
    );
    const item = screen.getByRole('listitem');
    expect(within(item).getByText('Signal alpha')).toBeInTheDocument();
    expect(within(item).getByText('Since yesterday')).toBeInTheDocument();
    expect(within(item).getByText('Please confirm')).toBeInTheDocument();
    expect(within(item).getByRole('button', { name: 'That’s right: Signal alpha' })).toBeInTheDocument();
    expect(within(item).getByRole('button', { name: 'Edit: Signal alpha' })).toBeInTheDocument();
    expect(within(item).getByRole('button', { name: 'Remove or correct: Signal alpha' })).toBeInTheDocument();
  });

  it('shows a chosen option in its own words and a duration once', () => {
    render(
      <ul>
        <ObservationChip
          observation={{ ...base, onset: undefined, presence: 'absent', value: 'none' }}
          optionLabels={{ none: 'None of these' }}
        />
        <ObservationChip
          observation={{
            ...base,
            observation_id: 'o2',
            onset: undefined,
            duration: '3 days',
            value: { value: 3, unit: 'days' },
          }}
        />
      </ul>,
    );
    const [chosen, lasting] = screen.getAllByRole('listitem');
    expect(within(chosen!).getByText('None of these')).toBeInTheDocument();
    expect(within(chosen!).queryByText('none')).not.toBeInTheDocument();
    expect(within(lasting!).getByText('3 days')).toBeInTheDocument();
    expect(within(lasting!).queryByText(/3 days · 3 days/)).not.toBeInTheDocument();
  });

  it('shows the user’s own phrase when the service kept it, and drops "That’s right" once confirmed', () => {
    render(
      <ul>
        <ObservationChip
          observation={{ ...base, raw_phrase: 'my own words', confirmed: true }}
          onConfirm={vi.fn()}
          onEdit={vi.fn()}
          onCorrect={vi.fn()}
        />
      </ul>,
    );
    expect(screen.getByText('my own words')).toBeInTheDocument();
    expect(screen.getByText('You confirmed this')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /That’s right/ })).not.toBeInTheDocument();
  });

  it('offers no structured edits for a detail that was not matched to a feature', () => {
    render(
      <ul>
        <ObservationChip
          observation={{ ...base, feature_id: null, raw_phrase: 'free words', presence: 'uncertain' }}
          onConfirm={vi.fn()}
          onEdit={vi.fn()}
          onCorrect={vi.fn()}
        />
      </ul>,
    );
    expect(screen.getByText('“free words”')).toBeInTheDocument();
    expect(screen.getByText('Saved as a note')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('SourceList', () => {
  const evidence = [
    {
      evidence_id: 'e1',
      source_title: 'Linked source',
      source_url: 'https://example.org/a',
      excerpt: 'Excerpt one.',
      knowledge_release: 'kr-1',
    },
    {
      evidence_id: 'e2',
      source_title: 'Unlinked source',
      source_url: null,
      excerpt: 'Excerpt two.',
      knowledge_release: 'kr-1',
    },
    {
      evidence_id: 'e3',
      source_title: 'Unsafe source',
      source_url: 'javascript:alert(1)',
      excerpt: 'Excerpt three.',
      knowledge_release: 'kr-1',
    },
  ];

  it('renders safe external links with an accessible label and no link for missing or unsafe URLs', () => {
    render(<SourceList evidence={evidence} defaultOpen />);

    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute('href', 'https://example.org/a');
    expect(links[0]).toHaveAttribute('target', '_blank');
    expect(links[0]).toHaveAttribute('rel', 'noopener noreferrer');
    expect(links[0]).toHaveAccessibleName('Open source: Linked source (opens in a new tab)');
    expect(screen.getAllByText('No link was supplied for this source.')).toHaveLength(2);
  });

  it('keeps the knowledge release out of patient-facing views', () => {
    const patient = render(<SourceList evidence={evidence} defaultOpen />);
    expect(screen.queryByText(/kr-1/)).not.toBeInTheDocument();
    patient.unmount();

    render(<SourceList evidence={evidence} defaultOpen showInternalDetail />);
    expect(screen.getAllByText('kr-1')).toHaveLength(3);
  });
});
