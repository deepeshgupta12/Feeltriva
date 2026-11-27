import { ArrowLeft, Sparkles } from 'lucide-react';
import { useEffect, useId, useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router';

import { toApiError, type ApiError } from '@/api/errors';
import type { Consent, Demographics } from '@/api/types';
import { InfoDialog } from '@/components/InfoDialog';
import { StatusPanel } from '@/components/StatusPanel';
import { Button, ButtonLink } from '@/components/ui/Button';
import { LINK_CLASSES } from '@/components/ui/buttonStyles';
import { SampleTag, StatusBadge } from '@/components/ui/StatusBadge';
import { SAMPLE_INTAKE_TEXT } from '@/fixtures/sampleContent';
import { cn } from '@/lib/cn';
import { errorCopy, errorReference } from '@/lib/errorCopy';
import { useAsync } from '@/lib/useAsync';
import type { AssessmentController } from '@/state/AssessmentController';
import { usePageMeta } from '@/state/hooks';
import { usePreferences } from '@/state/preferencesContext';
import { useServices } from '@/state/services';

const STEPS = ['About this check', 'A little context', 'Your symptoms'] as const;
const MAX_TEXT_LENGTH = 10_000;

type Subject = 'self_adult' | 'self_minor' | 'someone_else';
type GenderChoice = '' | 'woman' | 'man' | 'non_binary' | 'self_describe' | 'prefer_not';

const GENDER_OPTIONS: ReadonlyArray<{ value: GenderChoice; label: string }> = [
  { value: '', label: 'No answer' },
  { value: 'woman', label: 'Woman' },
  { value: 'man', label: 'Man' },
  { value: 'non_binary', label: 'Non-binary' },
  { value: 'self_describe', label: 'I use another term (describe below)' },
  { value: 'prefer_not', label: 'Prefer not to say' },
];

const GENDER_VALUES: Partial<Record<GenderChoice, string>> = {
  woman: 'Woman',
  man: 'Man',
  non_binary: 'Non-binary',
};

function ProgressLabel({ step }: { step: number }) {
  return (
    <ol aria-label="Steps" className="flex flex-wrap gap-x-4 gap-y-2 text-sm">
      {STEPS.map((label, index) => {
        const number = index + 1;
        const status = number < step ? 'Completed' : number === step ? 'Current step' : 'Not started';
        return (
          <li key={label} aria-current={number === step ? 'step' : undefined} className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className={cn(
                'inline-flex size-7 items-center justify-center rounded-full border text-sm font-semibold',
                number === step && 'border-primary bg-primary text-white',
                number < step && 'border-primary bg-teal-soft text-ink',
                number > step && 'border-line bg-surface text-ink-secondary',
              )}
            >
              {number}
            </span>
            <span className={cn('font-medium', number === step ? 'text-ink' : 'text-ink-secondary')}>
              {label}
              <span className="sr-only"> ({status})</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function FieldError({ id, message }: { id: string; message: string | null }) {
  if (!message) {
    return null;
  }
  return (
    <p id={id} role="alert" className="mt-1.5 text-[0.9375rem] font-medium text-urgent">
      {message}
    </p>
  );
}

/**
 * The terms and the agreement to them, basic context, then the first description of symptoms.
 * The terms are read from the service and shown word for word; a check cannot start without them.
 * Nothing the person enters is sent until the final step is submitted, and every answer is kept when
 * moving back or when a request fails.
 */
export function StartPage() {
  usePageMeta('Start a symptom check', { noindex: true });
  const id = useId();
  const navigate = useNavigate();
  const { assessment, registry, mock } = useServices();
  const { historyEnabled, trainingConsent, setTrainingConsent } = usePreferences();
  const headingRef = useRef<HTMLHeadingElement>(null);

  const [step, setStep] = useState(1);
  const [privacyOpen, setPrivacyOpen] = useState(false);

  // Step 1
  const terms = useAsync<Consent>('terms', () => assessment.getConsent());
  const currentTerms = terms.state.status === 'loaded' ? terms.state.data : null;
  const [acknowledged, setAcknowledged] = useState(false);
  const [acknowledgeError, setAcknowledgeError] = useState<string | null>(null);
  // The service refused the start because the terms had changed since they were shown.
  const [termsChanged, setTermsChanged] = useState(false);

  // Step 2
  const [subject, setSubject] = useState<Subject | null>(null);
  const [subjectError, setSubjectError] = useState<string | null>(null);
  const [age, setAge] = useState('');
  const [agePreferNot, setAgePreferNot] = useState(false);
  const [ageError, setAgeError] = useState<string | null>(null);
  const [gender, setGender] = useState<GenderChoice>('');
  const [genderDescription, setGenderDescription] = useState('');

  // Step 3
  const [text, setText] = useState('');
  const [sampleLoaded, setSampleLoaded] = useState(false);
  const [textError, setTextError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<ApiError | null>(null);
  // A session created by an earlier attempt is reused on retry instead of creating another.
  const createdController = useRef<AssessmentController | null>(null);

  const unsupportedScope = subject === 'self_minor' || subject === 'someone_else';

  // Moving between steps puts focus on the new step's heading.
  const previousStep = useRef(step);
  useEffect(() => {
    if (previousStep.current === step) {
      return;
    }
    previousStep.current = step;
    headingRef.current?.focus();
  }, [step]);

  const submitStepOne = (event: FormEvent) => {
    event.preventDefault();
    if (!currentTerms) {
      return;
    }
    if (!acknowledged) {
      setAcknowledgeError('Tick the box to confirm you’ve read this before continuing.');
      return;
    }
    setAcknowledgeError(null);
    setTermsChanged(false);
    setStep(2);
  };

  const submitStepTwo = (event: FormEvent) => {
    event.preventDefault();
    let valid = true;
    if (subject === null) {
      setSubjectError('Choose who this check is for.');
      valid = false;
    } else {
      setSubjectError(null);
    }
    if (unsupportedScope) {
      return;
    }
    if (!agePreferNot) {
      const trimmed = age.trim();
      const parsed = Number(trimmed);
      if (trimmed.length === 0) {
        setAgeError('Enter your age in years, or choose “Prefer not to answer”.');
        valid = false;
      } else if (!/^\d{1,3}$/.test(trimmed) || parsed > 130) {
        setAgeError('Enter your age as a whole number between 0 and 130.');
        valid = false;
      } else {
        setAgeError(null);
      }
    } else {
      setAgeError(null);
    }
    if (valid) {
      setStep(3);
    }
  };

  const buildDemographics = (): Demographics | undefined => {
    const demographics: Demographics = {};
    if (!agePreferNot && age.trim().length > 0) {
      demographics.age_years = Number(age.trim());
    }
    const genderValue = gender === 'self_describe' ? genderDescription.trim() : GENDER_VALUES[gender];
    if (genderValue) {
      demographics.gender_identity = genderValue.slice(0, 100);
    }
    return Object.keys(demographics).length > 0 ? demographics : undefined;
  };

  const submitStepThree = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting) {
      return;
    }
    const trimmed = text.trim();
    if (trimmed.length === 0) {
      setTextError('Describe what you’ve been feeling, or load the example.');
      return;
    }
    if (trimmed.length > MAX_TEXT_LENGTH) {
      setTextError(`Shorten your description to ${MAX_TEXT_LENGTH.toLocaleString('en-US')} characters or fewer.`);
      return;
    }
    if (!currentTerms) {
      // No agreement without the terms on screen.
      setStep(1);
      return;
    }
    setTextError(null);
    setSubmitError(null);
    setSubmitting(true);
    try {
      let controller = createdController.current;
      if (!controller) {
        const demographics = buildDemographics();
        const session = await assessment.startSession({
          // The version of the terms that were on screen when the box was ticked, and the separate choice.
          consent_version: currentTerms.version,
          training_consent: trainingConsent,
          ...(demographics ? { demographics } : {}),
        });
        controller = registry.create(session, { listed: historyEnabled });
        createdController.current = controller;
      }
      const accepted = await controller.sendText(trimmed);
      const state = controller.getSnapshot();
      if (accepted) {
        void navigate(`/assess/${controller.sessionId}`);
        return;
      }
      if (state.load === 'expired' || state.load === 'forbidden' || state.load === 'not_found') {
        // The session is no longer usable; the next attempt starts a fresh one.
        createdController.current = null;
        registry.forget(controller.sessionId);
      }
      setSubmitError(
        state.failure?.error ?? toApiError(new Error('Your description could not be sent. Please try again.')),
      );
    } catch (error) {
      const failed = toApiError(error);
      if (failed.code === 'consent_version_not_current') {
        // The terms changed while the form was being filled in. Nothing was started: the current terms are
        // read again and the agreement is asked for again. What was typed stays where it is.
        setAcknowledged(false);
        setTermsChanged(true);
        terms.reload();
        setStep(1);
      } else {
        setSubmitError(failed);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const failure = submitError ? errorCopy(submitError) : null;
  const reference = submitError ? errorReference(submitError) : null;

  return (
    <div className="mx-auto w-full max-w-[640px] px-4 py-8 sm:px-6 sm:py-12">
      <div className="rounded-card border border-line bg-surface p-5 sm:p-8">
        <ProgressLabel step={step} />
        <h1
          ref={headingRef}
          tabIndex={-1}
          className="mt-5 font-display text-[1.75rem] font-bold leading-tight text-ink"
        >
          {STEPS[step - 1]}
        </h1>

        {step === 1 ? (
          <form onSubmit={submitStepOne} noValidate className="mt-4 space-y-4">
            {termsChanged ? (
              <StatusPanel tone="attention" title="The terms have changed" announce="alert" headingLevel="h2">
                <p>
                  They changed while you were filling this in. Please read them again and tick the box to continue. What
                  you typed has been kept.
                </p>
              </StatusPanel>
            ) : null}

            {terms.state.status === 'loading' ? (
              <p role="status" className="text-ink-secondary">
                Loading the terms…
              </p>
            ) : null}

            {terms.state.status === 'failed' ? (
              <StatusPanel tone="attention" title="We couldn’t load the terms" announce="alert" headingLevel="h2">
                <p>A check can’t start until you have seen them. Nothing was sent.</p>
                <p>
                  <Button variant="secondary" size="sm" onClick={terms.reload}>
                    Try again
                  </Button>
                </p>
              </StatusPanel>
            ) : null}

            {currentTerms ? (
              <>
                <TermsText terms={currentTerms} />
                <p>
                  <button
                    type="button"
                    onClick={() => setPrivacyOpen(true)}
                    className={`min-h-11 text-left ${LINK_CLASSES}`}
                  >
                    Read the privacy details (draft)
                  </button>
                </p>

                <div>
                  <label className="flex cursor-pointer items-start gap-3 rounded-control border border-line p-4 hover:border-ink-muted">
                    <input
                      type="checkbox"
                      checked={acknowledged}
                      aria-invalid={acknowledgeError ? true : undefined}
                      aria-describedby={acknowledgeError ? `${id}-ack-error` : undefined}
                      onChange={(event) => {
                        setAcknowledged(event.target.checked);
                        setAcknowledgeError(null);
                      }}
                      className="mt-0.5 size-5 shrink-0 accent-primary"
                    />
                    <span className="font-medium text-ink">{currentTerms.acknowledgement}</span>
                  </label>
                  <FieldError id={`${id}-ack-error`} message={acknowledgeError} />
                </div>

                {/* A separate choice, never ticked for the person and never needed to continue. */}
                <div>
                  <label className="flex cursor-pointer items-start gap-3 rounded-control border border-line p-4 hover:border-ink-muted">
                    <input
                      type="checkbox"
                      checked={trainingConsent}
                      aria-describedby={`${id}-training-hint`}
                      onChange={(event) => setTrainingConsent(event.target.checked)}
                      className="mt-0.5 size-5 shrink-0 accent-primary"
                    />
                    <span>
                      <span className="font-medium text-ink">
                        {currentTerms.training.label} <span className="font-normal text-ink-secondary">(optional)</span>
                      </span>
                      <span id={`${id}-training-hint`} className="mt-1 block text-[0.9375rem] text-ink-secondary">
                        {currentTerms.training.explanation}
                      </span>
                    </span>
                  </label>
                </div>
              </>
            ) : null}

            <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-between">
              <ButtonLink
                to="/"
                variant="secondary"
                icon={<ArrowLeft aria-hidden="true" className="size-4 shrink-0" />}
              >
                Back to introduction
              </ButtonLink>
              {currentTerms ? <Button type="submit">Continue</Button> : null}
            </div>
          </form>
        ) : null}

        {step === 2 ? (
          <form onSubmit={submitStepTwo} noValidate className="mt-4 space-y-6">
            <fieldset>
              <legend className="font-semibold text-ink">Who is this check for?</legend>
              <div
                role="radiogroup"
                aria-describedby={subjectError ? `${id}-subject-error` : undefined}
                className="mt-2 space-y-2"
              >
                {(
                  [
                    { value: 'self_adult', label: 'Me, and I’m an adult' },
                    { value: 'self_minor', label: 'Me, and I’m not an adult yet' },
                    { value: 'someone_else', label: 'Someone else, for example a child or a person I care for' },
                  ] as const
                ).map((option) => (
                  <label
                    key={option.value}
                    className={cn(
                      'flex min-h-12 cursor-pointer items-center gap-3 rounded-control border px-3.5 py-2.5',
                      subject === option.value ? 'border-primary bg-teal-soft' : 'border-line hover:border-ink-muted',
                    )}
                  >
                    <input
                      type="radio"
                      name={`${id}-subject`}
                      value={option.value}
                      checked={subject === option.value}
                      onChange={() => {
                        setSubject(option.value);
                        setSubjectError(null);
                      }}
                      className="size-5 shrink-0 accent-primary"
                    />
                    <span className="font-medium text-ink">{option.label}</span>
                  </label>
                ))}
              </div>
              <FieldError id={`${id}-subject-error`} message={subjectError} />
            </fieldset>

            {unsupportedScope ? (
              <StatusPanel
                tone="attention"
                title="This check isn’t available for this situation yet"
                announce="status"
                headingLevel="h2"
              >
                <p>
                  Feeltriva currently supports adults checking their own symptoms. It can’t be used on behalf of someone
                  else, or by children and teenagers, and it won’t treat those situations as an adult self-check.
                </p>
                <p>If you’re concerned about someone’s health, please contact a health professional.</p>
              </StatusPanel>
            ) : (
              <>
                <div>
                  <label htmlFor={`${id}-age`} className="font-semibold text-ink">
                    Age in years
                  </label>
                  <p id={`${id}-age-hint`} className="text-[0.9375rem] text-ink-secondary">
                    Age can change which questions are relevant. Whether this check suits you is decided by the service,
                    not by this form.
                  </p>
                  <input
                    id={`${id}-age`}
                    type="text"
                    inputMode="numeric"
                    autoComplete="off"
                    value={age}
                    disabled={agePreferNot}
                    aria-invalid={ageError ? true : undefined}
                    aria-describedby={cn(`${id}-age-hint`, ageError && `${id}-age-error`)}
                    onChange={(event) => {
                      setAge(event.target.value);
                      setAgeError(null);
                    }}
                    className="field-control mt-2 max-w-[10rem]"
                  />
                  <label className="mt-2 flex min-h-11 cursor-pointer items-center gap-3">
                    <input
                      type="checkbox"
                      checked={agePreferNot}
                      onChange={(event) => {
                        setAgePreferNot(event.target.checked);
                        setAgeError(null);
                      }}
                      className="size-5 shrink-0 accent-primary"
                    />
                    <span className="text-ink">Prefer not to answer</span>
                  </label>
                  <FieldError id={`${id}-age-error`} message={ageError} />
                </div>

                <div>
                  <label htmlFor={`${id}-gender`} className="font-semibold text-ink">
                    Gender identity <span className="font-normal text-ink-secondary">(optional)</span>
                  </label>
                  <p id={`${id}-gender-hint`} className="text-[0.9375rem] text-ink-secondary">
                    If sex-related information is clinically relevant, you may be asked about it later, only when it
                    applies. Nothing about your body or pregnancy is assumed from your gender.
                  </p>
                  <select
                    id={`${id}-gender`}
                    value={gender}
                    aria-describedby={`${id}-gender-hint`}
                    onChange={(event) => setGender(event.target.value as GenderChoice)}
                    className="field-control mt-2"
                  >
                    {GENDER_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  {gender === 'self_describe' ? (
                    <div className="mt-3">
                      <label htmlFor={`${id}-gender-description`} className="font-medium text-ink">
                        How do you describe your gender?
                      </label>
                      <input
                        id={`${id}-gender-description`}
                        type="text"
                        maxLength={100}
                        autoComplete="off"
                        value={genderDescription}
                        onChange={(event) => setGenderDescription(event.target.value)}
                        className="field-control mt-1.5"
                      />
                    </div>
                  ) : null}
                </div>
              </>
            )}

            <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-between">
              <Button
                variant="secondary"
                onClick={() => setStep(1)}
                icon={<ArrowLeft aria-hidden="true" className="size-4 shrink-0" />}
              >
                Back
              </Button>
              {unsupportedScope ? (
                <ButtonLink to="/" variant="secondary">
                  Return to introduction
                </ButtonLink>
              ) : (
                <Button type="submit">Continue</Button>
              )}
            </div>
          </form>
        ) : null}

        {step === 3 ? (
          <form onSubmit={(event) => void submitStepThree(event)} noValidate className="mt-4 space-y-4">
            <div>
              <label htmlFor={`${id}-text`} className="font-display text-lg font-bold text-ink">
                What have you been feeling?
              </label>
              <p id={`${id}-text-hint`} className="mt-1 text-[0.9375rem] text-ink-secondary">
                {mock
                  ? 'Demo mode doesn’t analyse what you type. Whatever you enter, sample details are shown on the next screen.'
                  : 'You’ll be able to check and correct what was understood on the next screen.'}
              </p>
              <textarea
                id={`${id}-text`}
                rows={6}
                value={text}
                maxLength={MAX_TEXT_LENGTH}
                disabled={submitting}
                placeholder="Describe what feels different, when it started, and anything that makes it better or worse."
                aria-invalid={textError ? true : undefined}
                aria-describedby={cn(`${id}-text-hint`, textError && `${id}-text-error`)}
                onChange={(event) => {
                  setText(event.target.value);
                  setTextError(null);
                  if (event.target.value !== SAMPLE_INTAKE_TEXT) {
                    setSampleLoaded(false);
                  }
                }}
                className="field-control mt-2 min-h-40 resize-y"
              />
              <FieldError id={`${id}-text-error`} message={textError} />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={submitting}
                onClick={() => {
                  // Loads labelled sample text only. It is never submitted automatically.
                  setText(SAMPLE_INTAKE_TEXT);
                  setSampleLoaded(true);
                  setTextError(null);
                }}
                className="inline-flex min-h-11 items-center gap-2 rounded-full border border-primary/40 bg-teal-soft px-4 font-semibold text-ink hover:border-primary disabled:opacity-60"
              >
                <Sparkles aria-hidden="true" className="size-4 shrink-0 text-primary" />
                Try an example conversation
              </button>
              {sampleLoaded ? (
                <span role="status">
                  <SampleTag>Sample text loaded · review it, then continue</SampleTag>
                </span>
              ) : null}
            </div>

            {failure ? (
              <StatusPanel tone="attention" title={failure.title} announce="alert" headingLevel="h2">
                <p>{failure.message}</p>
                <p>Your description is still in the box above.</p>
                {reference ? <p className="text-sm">{reference}</p> : null}
              </StatusPanel>
            ) : null}

            <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-between">
              <Button
                variant="secondary"
                disabled={submitting}
                onClick={() => setStep(2)}
                icon={<ArrowLeft aria-hidden="true" className="size-4 shrink-0" />}
              >
                Back
              </Button>
              <Button type="submit" loading={submitting} loadingLabel="Starting your check…">
                {failure ? 'Try again' : 'Continue'}
              </Button>
            </div>
          </form>
        ) : null}
      </div>
      <InfoDialog page={privacyOpen ? 'privacy' : null} onClose={() => setPrivacyOpen(false)} />
    </div>
  );
}

/** The terms as the service gave them: every heading and paragraph, in order, with nothing added or left out. */
function TermsText({ terms }: { terms: Consent }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-display text-xl font-bold text-ink">{terms.title}</h2>
        {terms.status === 'draft' ? <StatusBadge tone="attention">Draft</StatusBadge> : null}
      </div>
      {terms.status === 'draft' ? (
        <p className="text-[0.9375rem] text-ink-secondary">
          These terms are a draft. The final wording has not been reviewed yet.
        </p>
      ) : null}
      {terms.sections.map((section) => (
        <section key={section.heading}>
          <h3 className="font-semibold text-ink">{section.heading}</h3>
          {section.paragraphs.map((paragraph) => (
            <p key={paragraph} className="mt-1 text-ink-secondary">
              {paragraph}
            </p>
          ))}
        </section>
      ))}
    </div>
  );
}
