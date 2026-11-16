/**
 * Route-level render tests: the whole app is rendered against the in-memory mock service
 * and driven the way a person would use it.
 */
import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DEMO_BANNER_TEXT } from '@/components/DemoBanner';
import { SAMPLE_INTAKE_TEXT } from '@/fixtures/sampleContent';
import { ALLOWED_STORAGE_KEYS, NAV_COLLAPSED_KEY } from '@/state/preferences';
import { currentObservations } from '@/state/selectors';
import { createTestServices, renderApp, seedScenario } from '@/test/harness';

const RESULT_ORDER = [
  'What to do next',
  'What we understood',
  'Possible explanations',
  'What is still uncertain',
  'Your consultation summary',
  'Sources',
];

function sectionHeadings(): string[] {
  return within(screen.getByRole('main'))
    .getAllByRole('heading', { level: 2 })
    .map((heading) => heading.textContent ?? '');
}

describe('demo banner', () => {
  it.each([
    '/',
    '/start',
    '/history',
    '/settings/privacy',
    '/conditions/demo.possibility_a',
    '/review',
    '/no-such-page',
  ])('is present on %s', async (route) => {
    renderApp(route);
    expect(await screen.findByText(DEMO_BANNER_TEXT)).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Demo notice' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument();
  });

  it('stays present on a result and on the consultation summary', async () => {
    const { services, sessionId } = await seedScenario('correction');
    const view = renderApp(`/results/${sessionId}`, services);
    expect(await screen.findByText(DEMO_BANNER_TEXT)).toBeInTheDocument();
    view.unmount();

    renderApp(`/summary/${sessionId}`, services);
    expect(await screen.findByText(DEMO_BANNER_TEXT)).toBeInTheDocument();
    // The export itself carries the demo label in its header and footer.
    const document_ = await screen.findByRole('article', { name: 'Consultation summary document' });
    expect(within(document_).getAllByText('Design demo · Sample information')).toHaveLength(2);
  });
});

describe('results screen', () => {
  it('renders the six sections in the required order', async () => {
    const { services, route } = await seedScenario('correction');
    renderApp(route, services);

    await screen.findByRole('heading', { level: 2, name: 'What to do next' });
    expect(sectionHeadings()).toEqual(RESULT_ORDER);
  });

  it('labels explanations as possible and sample, with no probability or diagnosis wording', async () => {
    const { services, route } = await seedScenario('correction');
    renderApp(route, services);

    const card = (await screen.findByRole('heading', { level: 3, name: 'Illustrative possibility A' })).closest(
      'article',
    )!;
    expect(within(card).getByText('Possible explanation')).toBeInTheDocument();
    expect(within(card).getByText('Sample · not a real condition')).toBeInTheDocument();
    expect(within(card).getByRole('heading', { name: 'Details that fit' })).toBeInTheDocument();
    expect(within(card).getByRole('heading', { name: 'Details that need clarification' })).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: /View supporting information/ })).toBeEnabled();

    const text = screen.getByRole('main').textContent ?? '';
    expect(text).not.toMatch(/\d\s?%/);
    expect(text).not.toMatch(/You have |Diagnosis confirmed|likely|probab/i);
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(screen.queryByRole('meter')).not.toBeInTheDocument();
  });

  it('marks the result stale after a correction and refreshes it on request', async () => {
    const { services, route, sessionId } = await seedScenario('correction');
    const { user } = renderApp(route, services);
    await screen.findByRole('heading', { level: 3, name: 'Illustrative possibility B' });

    await user.click(screen.getByRole('button', { name: 'Remove or correct: Sample symptom B' }));
    const dialog = await screen.findByRole('dialog', { name: 'Remove or correct this detail' });
    // Nothing is preselected in a correction.
    for (const radio of within(dialog).getAllByRole('radio')) {
      expect(radio).not.toBeChecked();
    }
    await user.click(within(dialog).getByRole('radio', { name: /I don’t have this/ }));
    await user.click(within(dialog).getByRole('button', { name: 'Save change' }));

    expect(await screen.findByRole('heading', { name: 'This result needs updating' })).toBeInTheDocument();
    // A stale result cannot imply it is current: no primary action, explanation actions disabled.
    expect(screen.queryByRole('link', { name: 'Prepare consultation summary' })).not.toBeInTheDocument();
    for (const button of screen.getAllByRole('button', { name: /View supporting information/ })) {
      expect(button).toBeDisabled();
    }
    const requestsBefore = services.mock.requestLog.filter((entry) => entry.path.endsWith('/assessments')).length;

    await user.click(screen.getByRole('button', { name: 'Update result' }));

    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'This result needs updating' })).not.toBeInTheDocument(),
    );
    expect(services.mock.requestLog.filter((entry) => entry.path.endsWith('/assessments'))).toHaveLength(
      requestsBefore + 1,
    );
    expect(screen.queryByRole('heading', { level: 3, name: 'Illustrative possibility B' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Prepare consultation summary' })).toBeInTheDocument();
    expect(services.registry.get(sessionId)?.controller.getSnapshot().session?.state).toBe('result_ready');
  });

  it('shows no reassurance when information is insufficient', async () => {
    const { services, route } = await seedScenario('insufficient');
    renderApp(route, services);

    await screen.findByRole('heading', { level: 2, name: 'What to do next' });
    const main = screen.getByRole('main');
    expect(within(main).getByText(/This is an incomplete result, not a\s+reassuring one/)).toBeInTheDocument();
    expect(within(main).getAllByText('Urgency not assessed').length).toBeGreaterThan(0);
    expect(within(main).getByText(/This does not mean your situation is low urgency/)).toBeInTheDocument();
    // No normal / routine / low-risk badge anywhere.
    expect(within(main).queryByText('Routine')).not.toBeInTheDocument();
    expect(within(main).queryByText(/low risk|looks fine|nothing to worry|normal result/i)).not.toBeInTheDocument();
    // No explanation cards; what is missing is explained and the next approved question is offered.
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    expect(within(main).getByText(/None are shown, because there isn’t enough information/)).toBeInTheDocument();
    expect(
      within(main).getByText(/Sample missing detail: the sample measurement has not been provided/),
    ).toBeInTheDocument();
    expect(within(main).getByRole('link', { name: 'Answer the next question' })).toBeInTheDocument();
  });

  it('withholds a candidate explanation when its evidence is missing', async () => {
    const { services, route, sessionId } = await seedScenario('evidence_missing');
    renderApp(route, services);

    expect(await screen.findByRole('heading', { name: 'Incomplete result' })).toBeInTheDocument();
    // The service did send the candidate; the screen refuses to render it without support.
    const assessment = services.registry.get(sessionId)?.controller.getSnapshot().assessment;
    expect(assessment?.candidates.map((candidate) => candidate.name)).toEqual(['Illustrative possibility A']);
    expect(screen.queryByRole('heading', { name: 'Illustrative possibility A' })).not.toBeInTheDocument();
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    expect(screen.getByText('No sources were supplied with this result.')).toBeInTheDocument();
  });

  it('shows no result and no guess when the assessment service is unavailable', async () => {
    const { services, route } = await seedScenario('unavailable');
    const { user } = renderApp(route, services);

    expect(await screen.findByRole('heading', { name: 'We couldn’t complete this assessment' })).toBeInTheDocument();
    expect(sectionHeadings()).toEqual(['We couldn’t complete this assessment', 'What we understood']);
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View consultation summary' })).toBeInTheDocument();

    // Opening the page did not trigger a hidden retry, and a manual retry still invents nothing.
    const attempts = () => services.mock.requestLog.filter((entry) => entry.path.endsWith('/assessments')).length;
    const before = attempts();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(attempts()).toBe(before + 1));
    expect(screen.getByRole('heading', { name: 'We couldn’t complete this assessment' })).toBeInTheDocument();

    services.mock.setOutage(false);
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { level: 2, name: 'What to do next' })).toBeInTheDocument();
  });
});

describe('urgent handoff', () => {
  it('stops routine questioning in the conversation and announces the urgent state once', async () => {
    const { services, route } = await seedScenario('urgent');
    renderApp(route, services);

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByRole('heading', { name: 'This needs urgent attention' })).toBeInTheDocument();
    expect(within(alert).getByText('Urgent-state preview')).toBeInTheDocument();
    expect(within(alert).getByText('Sample action text')).toBeInTheDocument();
    expect(within(alert).getByText(/Sample urgent action: placeholder text/)).toBeInTheDocument();
    expect(screen.getAllByRole('alert')).toHaveLength(1);

    expect(screen.queryByText('Follow-up question')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send answer' })).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(
      screen.getByText(/Routine questions are paused\. You can still check and correct your details/),
    ).toBeInTheDocument();
    // No hardcoded emergency number, and no claim that anyone was called.
    expect(screen.getByRole('main').textContent).not.toMatch(/\b(911|999|112|000)\b|we(’|')ve called|calling/i);
  });

  it('shows no explanation cards on the urgent result', async () => {
    const { services, sessionId } = await seedScenario('urgent');
    renderApp(`/results/${sessionId}`, services);

    await screen.findByRole('heading', { level: 2, name: 'What to do next' });
    expect(sectionHeadings()).toEqual(['What to do next', 'What we understood', 'Your consultation summary']);
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
  });
});

describe('version conflict in the conversation', () => {
  it('refreshes, keeps the unsent answer and asks for it to be sent again', async () => {
    const { services, route, sessionId } = await seedScenario('conflict');
    const { user } = renderApp(route, services);

    await screen.findByRole('heading', { name: /have you also noticed sample symptom C/ });
    await user.click(screen.getByRole('radio', { name: 'Yes' }));
    await user.click(screen.getByRole('button', { name: 'Send answer' }));

    expect((await screen.findAllByText('Your details changed. Refreshing this assessment…')).length).toBeGreaterThan(0);
    expect(
      await screen.findByText('Your answer wasn’t sent. Check it still applies, then send it again.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Yes' })).toBeChecked();
    const controller = services.registry.get(sessionId)!.controller;
    // Nothing was attached to the session by the rejected answer.
    expect(
      currentObservations(controller.getSnapshot().session).some((item) => item.feature_id === 'fx.signal_gamma'),
    ).toBe(false);

    await user.click(screen.getByRole('button', { name: 'Send answer' }));
    expect(await screen.findByRole('heading', { name: /how long have you had sample symptom A/ })).toBeInTheDocument();
    expect(
      currentObservations(controller.getSnapshot().session).some((item) => item.feature_id === 'fx.signal_gamma'),
    ).toBe(true);
  });
});

describe('start screen', () => {
  it('requires an explicit acknowledgement and never preselects context answers', async () => {
    const { user, services } = renderApp('/start');

    const acknowledgement = screen.getByRole('checkbox', { name: /I understand that this is a demo/ });
    expect(acknowledgement).not.toBeChecked();
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Tick the box to confirm');
    expect(screen.getByRole('heading', { level: 1, name: 'About this check' })).toBeInTheDocument();

    await user.click(acknowledgement);
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    expect(screen.getByRole('heading', { level: 1, name: 'A little context' })).toBeInTheDocument();
    for (const radio of screen.getAllByRole('radio')) {
      expect(radio).not.toBeChecked();
    }
    expect(screen.getByLabelText('Age in years')).toHaveValue('');
    expect(screen.getByRole('checkbox', { name: 'Prefer not to answer' })).not.toBeChecked();

    // Caregiver / minor flows get an explicit unsupported state, not silent adult treatment.
    await user.click(screen.getByRole('radio', { name: /Someone else/ }));
    expect(
      screen.getByRole('heading', { name: 'This check isn’t available for this situation yet' }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Continue' })).not.toBeInTheDocument();
    expect(services.mock.requestLog).toHaveLength(0);
  });

  it('loads the example without submitting it, and keeps the text when the request fails', async () => {
    const { user, services } = renderApp('/start');
    await user.click(screen.getByRole('checkbox', { name: /I understand that this is a demo/ }));
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    await user.click(screen.getByRole('radio', { name: /Me, and I’m an adult/ }));
    await user.click(screen.getByRole('checkbox', { name: 'Prefer not to answer' }));
    await user.click(screen.getByRole('button', { name: 'Continue' }));

    await user.click(screen.getByRole('button', { name: 'Try an example conversation' }));
    const textarea = screen.getByLabelText('What have you been feeling?');
    expect(textarea).toHaveValue(SAMPLE_INTAKE_TEXT);
    expect(screen.getByText(/Sample text loaded/)).toBeInTheDocument();
    // Loading the chip created no session and sent nothing.
    expect(services.mock.requestLog).toHaveLength(0);
    expect(screen.getByRole('heading', { level: 1, name: 'Your symptoms' })).toBeInTheDocument();

    services.mock.setOffline(true);
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    expect(await screen.findByRole('heading', { name: 'You appear to be offline' })).toBeInTheDocument();
    expect(textarea).toHaveValue(SAMPLE_INTAKE_TEXT);

    services.mock.setOffline(false);
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('heading', { name: /have you also noticed sample symptom C/ })).toBeInTheDocument();
    // "Prefer not to answer" means no age was sent or guessed.
    const [entry] = services.registry.getSnapshot();
    expect(entry?.controller.getSnapshot().session?.demographics).toBeUndefined();
  });
});

describe('browser storage', () => {
  it('writes no health data to storage across a full assessment', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    const { user } = renderApp('/start');

    await user.click(screen.getByRole('checkbox', { name: /I understand that this is a demo/ }));
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    await user.click(screen.getByRole('radio', { name: /Me, and I’m an adult/ }));
    await user.type(screen.getByLabelText('Age in years'), '41');
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    await user.type(screen.getByLabelText('What have you been feeling?'), 'private words that must never be stored');
    await user.click(screen.getByRole('button', { name: 'Continue' }));

    await screen.findByRole('heading', { name: /have you also noticed sample symptom C/ });
    await user.click(screen.getByRole('button', { name: 'That’s right: Sample symptom A' }));
    await screen.findByText('You confirmed this');
    await user.click(screen.getByRole('radio', { name: 'No' }));
    await user.click(screen.getByRole('button', { name: 'Send answer' }));

    await screen.findByRole('heading', { name: /how long have you had sample symptom A/ });
    await user.type(screen.getByRole('textbox', { name: 'How long' }), '3');
    await user.selectOptions(screen.getByLabelText('Unit of time'), 'days');
    await user.click(screen.getByRole('button', { name: 'Send answer' }));

    await screen.findByRole('heading', { name: /how much does sample symptom B affect your day/ });
    await user.click(screen.getByRole('radio', { name: 'A moderate amount' }));
    await user.click(screen.getByRole('button', { name: 'Send answer' }));

    await screen.findByRole('heading', { name: /which of these sample situations apply/ });
    await user.click(screen.getByRole('checkbox', { name: 'Sample situation 1' }));
    await user.click(screen.getByRole('button', { name: 'Send answer' }));

    await user.type(await screen.findByLabelText('Add more details'), 'another private note');
    await user.click(screen.getByRole('button', { name: 'Send' }));
    await screen.findByText('another private note');

    await user.click(await screen.findByRole('button', { name: 'See your next step' }));
    await screen.findByRole('heading', { level: 2, name: 'What to do next' });
    await user.click(screen.getByRole('link', { name: 'Prepare consultation summary' }));
    await screen.findByRole('heading', { name: 'Reported symptoms' });

    // Nothing at all has been stored so far.
    expect(setItem).not.toHaveBeenCalled();
    expect(window.localStorage).toHaveLength(0);
    expect(window.sessionStorage).toHaveLength(0);
    expect(document.cookie).toBe('');

    // The one permitted write: a non-sensitive interface preference.
    await user.click(screen.getByRole('button', { name: 'Collapse navigation' }));
    expect(Object.keys(window.localStorage)).toEqual([NAV_COLLAPSED_KEY]);
    expect(window.localStorage.getItem(NAV_COLLAPSED_KEY)).toBe('true');
    expect(window.sessionStorage).toHaveLength(0);
    for (const [key, value] of setItem.mock.calls) {
      expect(ALLOWED_STORAGE_KEYS).toContain(key);
      expect(value).toMatch(/^(true|false)$/);
    }

    // Private text never reaches the page title or the URL either.
    expect(document.title).toBe('Consultation summary · Feeltriva');
    expect(document.title).not.toMatch(/sample symptom|private/i);
  });

  it('holds session state in memory only: a fresh page load cannot see an earlier session', async () => {
    const { services, sessionId } = await seedScenario('correction');
    expect(services.registry.get(sessionId)).toBeDefined();

    // A reload builds new services. Nothing was persisted, so the session is simply gone.
    renderApp(`/assess/${sessionId}`, createTestServices());

    expect(await screen.findByRole('heading', { name: 'We couldn’t find this assessment' })).toBeInTheDocument();
    expect(screen.queryByText('Sample symptom A')).not.toBeInTheDocument();
  });
});

describe('consultation summary', () => {
  it('requires the review acknowledgement before any export and copies only on an explicit click', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    const { services, sessionId } = await seedScenario('correction');
    // user-event provides an in-memory clipboard, read back below.
    const { user } = renderApp(`/summary/${sessionId}`, services);

    await screen.findByRole('heading', { name: 'Reported symptoms' });
    expect(await navigator.clipboard.readText()).toBe('');
    expect(print).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Copy text' }));
    await user.click(screen.getByRole('button', { name: 'Print or save as PDF' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Tick the box to confirm you’ve reviewed the summary first.');
    expect(await navigator.clipboard.readText()).toBe('');
    expect(print).not.toHaveBeenCalled();

    await user.click(screen.getByRole('checkbox', { name: /I’ve reviewed this summary/ }));
    await user.click(screen.getByRole('button', { name: 'Copy text' }));
    expect(await screen.findByText('Summary text copied to your clipboard.')).toBeInTheDocument();
    const copied = await navigator.clipboard.readText();
    expect(copied.startsWith('Design demo · Sample information')).toBe(true);
    expect(copied.trimEnd().endsWith('Design demo · Sample information')).toBe(true);
    // What the person reported is kept apart from the provisional explanations.
    expect(copied.indexOf('== Reported by you ==')).toBeLessThan(
      copied.indexOf('== From the assessment (provisional) =='),
    );
    expect(copied.indexOf('Reported symptoms')).toBeLessThan(
      copied.indexOf('Provisional explanations (not a diagnosis)'),
    );
    expect(copied).toContain('Sample symptom C');

    await user.click(screen.getByRole('button', { name: 'Print or save as PDF' }));
    expect(print).toHaveBeenCalledTimes(1);

    // Unavailable integrations are labelled, not faked.
    await user.click(screen.getByRole('button', { name: 'Share…' }));
    const share = await screen.findByRole('dialog', { name: 'Share this summary' });
    expect(within(share).getAllByText('Unavailable')).toHaveLength(3);
  });
});

describe('history', () => {
  it('goes from empty history to a sample, then deletion with an accurate receipt', async () => {
    const { user, services } = renderApp('/history');

    expect(screen.getByRole('heading', { name: 'No saved assessments yet' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Start a sample assessment' }));

    const title = await screen.findByRole('heading', { name: 'Sample assessment 1' });
    const card = title.closest('li')!;
    expect(within(card).getByText('Completed')).toBeInTheDocument();
    expect(within(card).getByText('A consultation summary is available.')).toBeInTheDocument();
    // A past provisional explanation is not presented as medical history.
    expect(card.textContent).not.toMatch(/Illustrative possibility/);

    await user.click(within(card).getByRole('button', { name: 'Delete: Sample assessment 1' }));
    const confirm = await screen.findByRole('alertdialog', { name: 'Delete this assessment?' });
    await user.click(within(confirm).getByRole('button', { name: 'Delete assessment' }));

    expect(await screen.findByRole('heading', { name: 'Deletion scheduled' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Deletion completed' })).not.toBeInTheDocument();
    expect(screen.getByText(/has not confirmed that deletion is finished yet/)).toBeInTheDocument();
    expect(screen.getByText(/^demo-receipt-/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'No saved assessments yet' })).toBeInTheDocument();
    expect(services.mock.requestLog.filter((entry) => entry.method === 'DELETE')).toHaveLength(1);
  });
});

describe('internal review', () => {
  it('is gated behind the reviewer preview and says the gate is not authorization', async () => {
    renderApp('/review/data');

    expect(await screen.findByRole('heading', { name: 'Reviewer access is required' })).toBeInTheDocument();
    expect(screen.getByText(/The preview switch is not real authorization/)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('shows the imported dataset audit facts and saves a demo note on a repeated header', async () => {
    const { user } = renderApp('/');
    await user.click(screen.getByRole('button', { name: 'Demo tools' }));
    const tools = await screen.findByRole('dialog', { name: 'Demo tools' });
    await user.click(within(tools).getByRole('button', { name: /Internal reviewer/ }));

    expect(await screen.findByRole('heading', { level: 1, name: 'Data quality' })).toBeInTheDocument();
    expect(screen.getByText('Internal review')).toBeInTheDocument();
    const table = await screen.findByRole('table');
    // All 37 repeated header names from the audit, plus the header row.
    expect(within(table).getAllByRole('row')).toHaveLength(38);

    await user.click(within(table).getByRole('button', { name: 'View details for vomiting' }));
    const drawer = await screen.findByRole('dialog', { name: 'vomiting' });
    expect(within(drawer).getByText(/Column 12:/)).toBeInTheDocument();
    expect(within(drawer).getByText(/Column 601:/)).toBeInTheDocument();
    expect(within(drawer).getByText(/values disagree in 22,272 rows/)).toBeInTheDocument();
    await user.type(within(drawer).getByLabelText('Add a note'), 'Columns disagree; needs reconciliation.');
    await user.click(within(drawer).getByRole('button', { name: 'Save demo note' }));
    expect(await within(drawer).findByText('Demo note saved. It is kept in memory only.')).toBeInTheDocument();
    expect(within(drawer).getByText('Columns disagree; needs reconciliation.')).toBeInTheDocument();
    expect(within(drawer).getByText('Demo change')).toBeInTheDocument();
  });

  it('labels audit figures as imported dataset audit and keeps research metrics research-only', async () => {
    const { user } = renderApp('/');
    await user.click(screen.getByRole('button', { name: 'Demo tools' }));
    const tools = await screen.findByRole('dialog', { name: 'Demo tools' });
    await user.click(within(tools).getByRole('switch', { name: 'Reviewer preview' }));
    await user.click(within(tools).getByRole('link', { name: /Open internal review/ }));

    expect(await screen.findByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
    for (const figure of ['6', '960', '37', '27,622']) {
      expect(await screen.findByText(figure)).toBeInTheDocument();
    }
    expect(screen.getAllByText('Imported dataset audit')).toHaveLength(4);
    expect(screen.getByText(/Not clinically approved conditions/)).toBeInTheDocument();
    expect(screen.getByText(/Not a count of unique patients/)).toBeInTheDocument();

    await user.click(screen.getByRole('link', { name: 'Model evaluation' }));
    expect(await screen.findByText('Baseline rejected for clinical serving.')).toBeInTheDocument();
    expect(screen.getByText('Research only')).toBeInTheDocument();
    for (const value of ['15.71%', '20.56%', '39.67%', '39 / 46']) {
      expect(screen.getByText(value)).toBeInTheDocument();
    }
    expect(screen.getAllByText('Not evaluated')).toHaveLength(3);
    expect(screen.queryByText('0%')).not.toBeInTheDocument();

    await user.click(screen.getByRole('link', { name: 'Releases' }));
    expect(await screen.findByRole('button', { name: 'Publish release' })).toBeDisabled();
    expect(screen.getByText(/Publishing is disabled\./)).toBeInTheDocument();
  });
});

describe('condition information', () => {
  it('hides sections that have no reviewed content', async () => {
    renderApp('/conditions/demo.possibility_b');

    expect(await screen.findByRole('heading', { level: 1, name: 'Illustrative possibility B' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Sources' })).toBeInTheDocument();
    for (const hidden of [
      'Symptoms',
      'Causes and risk context',
      'Management information',
      'Questions to ask a clinician',
    ]) {
      expect(screen.queryByRole('heading', { name: hidden })).not.toBeInTheDocument();
    }
    expect(screen.getByText('Design demo · Placeholder content')).toBeInTheDocument();
  });

  it('shows nothing rather than a guess for an unknown condition', async () => {
    renderApp('/conditions/not-a-real-id');
    expect(await screen.findByRole('heading', { name: 'No reviewed information is available' })).toBeInTheDocument();
  });
});
