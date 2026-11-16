import { ArrowRight, RotateCcw, Shuffle } from 'lucide-react';
import { Link, useLocation } from 'react-router';

import { DEMO_SCENARIOS, findScenario, type ScenarioId } from '@/fixtures/scenarios';
import { cn } from '@/lib/cn';
import { useDemo } from '@/state/demo';

import { Sheet } from './ui/Sheet';
import { Switch } from './ui/Switch';

interface DemoToolbarProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const SESSION_ROUTE = /^\/(?:assess|results|summary)\/([^/]+)/;

/**
 * Development-only scenario switcher and state toggles. Styled as a dark tools panel so
 * it cannot be mistaken for part of the patient workflow. Scenarios change UI state
 * deterministically; nothing here analyses typed text.
 */
export function DemoToolbar({ open, onOpenChange }: DemoToolbarProps) {
  const demo = useDemo();
  const location = useLocation();
  const sessionId = SESSION_ROUTE.exec(location.pathname)?.[1] ?? null;
  const active = demo.activeScenario ? findScenario(demo.activeScenario) : null;

  const choose = (scenario: ScenarioId) => {
    void demo.runScenario(scenario).then(() => onOpenChange(false));
  };

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      side="right"
      tone="tools"
      title="Demo tools"
      description="Development-only controls. Not part of the product and not a security boundary."
    >
      <div className="space-y-6 text-white">
        <section aria-labelledby="demo-scenarios-heading">
          <h3 id="demo-scenarios-heading" className="font-display text-base font-bold text-white">
            Sample scenarios
          </h3>
          {demo.scenariosAvailable ? (
            <p className="mt-1 text-sm text-white/85">
              Choosing a scenario resets the demo and loads sample data. Nothing you type changes the outcome.
            </p>
          ) : (
            <p className="mt-1 rounded-control border border-white/30 p-3 text-sm text-white/90">
              Scenarios need the in-memory mock service (<code>VITE_SERVICE_MODE=mock</code>). This build is connected
              to an API, so content comes from the server.
            </p>
          )}
          <ol className="mt-3 space-y-2">
            {DEMO_SCENARIOS.map((scenario) => {
              const isActive = demo.activeScenario === scenario.id;
              return (
                <li key={scenario.id}>
                  <button
                    type="button"
                    disabled={!demo.scenariosAvailable || demo.scenarioLoading}
                    aria-current={isActive ? 'true' : undefined}
                    onClick={() => choose(scenario.id)}
                    className={cn(
                      'flex min-h-11 w-full items-start gap-3 rounded-control border px-3 py-2.5 text-left transition-colors duration-150 disabled:opacity-50',
                      isActive ? 'border-white bg-white/15' : 'border-white/25 hover:bg-white/10',
                    )}
                  >
                    <span
                      aria-hidden="true"
                      className="mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-full border border-white/50 text-xs font-semibold"
                    >
                      {scenario.number ?? '+'}
                    </span>
                    <span className="min-w-0">
                      <span className="block font-semibold">
                        {scenario.title}
                        {isActive ? <span className="font-normal text-white/85"> (loaded)</span> : null}
                      </span>
                      <span className="block text-sm text-white/85">{scenario.description}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
          {active ? (
            <p className="mt-3 rounded-control bg-white/10 p-3 text-sm" role="status">
              <span className="font-semibold">Try this: </span>
              {active.hint}
            </p>
          ) : null}
        </section>

        <section aria-labelledby="demo-states-heading" className="space-y-4 border-t border-white/20 pt-5">
          <h3 id="demo-states-heading" className="font-display text-base font-bold text-white">
            Simulated conditions
          </h3>
          <Switch
            tone="tools"
            label="Simulate offline"
            description="Every request fails as if the network were unreachable."
            checked={demo.offline}
            onCheckedChange={demo.setOffline}
            disabled={!demo.scenariosAvailable}
          />
          <Switch
            tone="tools"
            label="Service outage"
            description="Assessment requests fail with “unavailable”. Details and summaries still work."
            checked={demo.outage}
            onCheckedChange={demo.setOutage}
            disabled={!demo.scenariosAvailable}
          />
          <button
            type="button"
            disabled={!demo.scenariosAvailable || !sessionId}
            onClick={() => {
              if (sessionId) {
                demo.simulateConcurrentUpdate(sessionId);
                onOpenChange(false);
              }
            }}
            className="flex min-h-11 w-full items-center gap-2 rounded-control border border-white/25 px-3 py-2 text-left font-medium hover:bg-white/10 disabled:opacity-50"
          >
            <Shuffle aria-hidden="true" className="size-4 shrink-0" />
            <span>
              Simulate an update from another tab
              <span className="block text-sm font-normal text-white/85">
                {sessionId ? 'Your next change will hit a version conflict.' : 'Open a conversation or result first.'}
              </span>
            </span>
          </button>
        </section>

        <section aria-labelledby="demo-review-heading" className="space-y-3 border-t border-white/20 pt-5">
          <h3 id="demo-review-heading" className="font-display text-base font-bold text-white">
            Internal screens
          </h3>
          <Switch
            tone="tools"
            label="Reviewer preview"
            description="Shows the internal review workspace. This switch is not authorization: production needs backend roles and protected routes."
            checked={demo.reviewerPreview}
            onCheckedChange={demo.setReviewerPreview}
          />
          {demo.reviewerPreview ? (
            <Link
              to="/review"
              onClick={() => onOpenChange(false)}
              className="inline-flex min-h-11 items-center gap-2 font-semibold underline underline-offset-4"
            >
              Open internal review
              <ArrowRight aria-hidden="true" className="size-4" />
            </Link>
          ) : null}
        </section>

        <section className="border-t border-white/20 pt-5">
          <button
            type="button"
            onClick={() => {
              demo.resetDemo();
              onOpenChange(false);
            }}
            className="flex min-h-11 w-full items-center justify-center gap-2 rounded-control border border-white/60 px-3 py-2 font-semibold hover:bg-white/10"
          >
            <RotateCcw aria-hidden="true" className="size-4" />
            Reset demo
          </button>
          <p className="mt-2 text-sm text-white/85">
            Clears every sample session held in memory. Reloading the page does the same.
          </p>
        </section>
      </div>
    </Sheet>
  );
}
