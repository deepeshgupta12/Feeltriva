import { lazy, Suspense, useEffect, useRef } from 'react';
import { Route, Routes, useLocation } from 'react-router';

import { AppShell } from './components/AppShell';
import { DemoBanner } from './components/DemoBanner';
import { PublicLayout } from './components/PublicLayout';
import { AssessPage } from './routes/AssessPage';
import { ConditionPage } from './routes/ConditionPage';
import { HistoryPage } from './routes/HistoryPage';
import { LandingPage } from './routes/LandingPage';
import { NotFoundPage } from './routes/NotFoundPage';
import { PrivacyPage } from './routes/PrivacyPage';
import { ResultsPage } from './routes/ResultsPage';
import { StartPage } from './routes/StartPage';
import { SummaryPage } from './routes/SummaryPage';

const ReviewRoutes = lazy(() => import('./routes/review/ReviewRoutes'));

/**
 * After a route change, scroll to the top and move focus to the new page's heading so
 * keyboard and screen-reader users land at the start of the new content.
 */
function RouteFocus() {
  const { pathname, hash } = useLocation();
  const previousPath = useRef(pathname);

  useEffect(() => {
    // Only react to an actual change of page (not the first render, and not a re-run of
    // this effect for the same path).
    if (previousPath.current === pathname) {
      return;
    }
    previousPath.current = pathname;
    if (hash) {
      return;
    }
    window.scrollTo(0, 0);
    document.querySelector<HTMLElement>('main h1')?.focus({ preventScroll: true });
  }, [pathname, hash]);

  return null;
}

export function App() {
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[60] focus:rounded-control focus:bg-surface focus:px-4 focus:py-3 focus:font-semibold focus:text-ink focus:shadow-float"
      >
        Skip to main content
      </a>
      <DemoBanner />
      <RouteFocus />
      <Routes>
        <Route element={<PublicLayout />}>
          <Route index element={<LandingPage />} />
          <Route path="start" element={<StartPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>

        <Route element={<AppShell />}>
          <Route path="assess/:sessionId" element={<AssessPage />} />
          <Route path="results/:sessionId" element={<ResultsPage />} />
          <Route path="summary/:sessionId" element={<SummaryPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="conditions/:diseaseId" element={<ConditionPage />} />
          <Route path="settings/privacy" element={<PrivacyPage />} />
        </Route>

        {/* Internal reviewer workspace. The preview switch is not authorization. */}
        <Route
          path="review/*"
          element={
            <Suspense
              fallback={
                <main id="main-content" className="mx-auto w-full max-w-[760px] flex-1 px-4 py-10 sm:px-6">
                  <p role="status" className="text-ink-secondary">
                    Loading internal review…
                  </p>
                </main>
              }
            >
              <ReviewRoutes />
            </Suspense>
          }
        />
      </Routes>
    </div>
  );
}
