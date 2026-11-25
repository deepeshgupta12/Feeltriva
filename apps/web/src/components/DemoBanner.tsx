import { FlaskConical, SlidersHorizontal } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { useDemo } from '@/state/demo';
import { useServices } from '@/state/services';

import { DemoToolbar } from './DemoToolbar';

export const DEMO_BANNER_TEXT = 'Design demo · Sample scenarios · Not a medical assessment.';
export const DEMO_EXPORT_LABEL = 'Design demo · Sample information';
/** In live mode nothing shown is a sample scenario: the app talks to the service on this computer. */
export const LIVE_BANNER_TEXT = 'Test version · Connected to the service on this computer · Not a medical assessment.';

/**
 * Persistent demo notice shown on every screen. It also hosts the entry point to the
 * development-only demo tools, which keeps them visually apart from the patient workflow
 * and clear of the mobile composer.
 *
 * The banner publishes its height as `--demo-banner-height` so sticky headers and rails
 * can sit directly beneath it at any text size.
 */
export function DemoBanner() {
  const { toolsEnabled } = useDemo();
  const { config } = useServices();
  const [toolsOpen, setToolsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) {
      return;
    }
    const publish = () => {
      // On very short viewports the banner is not sticky, so nothing needs to sit beneath it.
      const sticky = window.getComputedStyle(element).position === 'sticky';
      document.documentElement.style.setProperty('--demo-banner-height', sticky ? `${element.offsetHeight}px` : '0px');
    };
    publish();
    window.addEventListener('resize', publish);
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(publish);
    observer?.observe(element);
    return () => {
      window.removeEventListener('resize', publish);
      observer?.disconnect();
    };
  }, []);

  return (
    <div
      ref={ref}
      role="region"
      aria-label="Demo notice"
      className="sticky top-0 z-40 border-b border-attention/25 bg-attention-soft text-attention [@media(max-height:560px)]:static print:hidden"
    >
      <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-3 px-4 py-1 sm:px-6">
        <p className="flex items-start gap-2 py-1.5 text-sm font-medium">
          <FlaskConical aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span>{config.serviceMode === 'http' ? LIVE_BANNER_TEXT : DEMO_BANNER_TEXT}</span>
        </p>
        {toolsEnabled ? (
          <button
            type="button"
            onClick={() => setToolsOpen(true)}
            className="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center gap-1.5 rounded-control border border-dashed border-attention/60 px-3 text-sm font-semibold hover:bg-attention/10"
          >
            <SlidersHorizontal aria-hidden="true" className="size-4" />
            <span className="max-sm:sr-only">Demo tools</span>
          </button>
        ) : null}
      </div>
      {toolsEnabled ? <DemoToolbar open={toolsOpen} onOpenChange={setToolsOpen} /> : null}
    </div>
  );
}
