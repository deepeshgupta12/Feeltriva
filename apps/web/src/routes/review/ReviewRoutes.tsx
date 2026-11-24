import { Route, Routes } from 'react-router';

import { useServices } from '@/state/services';

import { LiveClaimsPage } from './live/LiveClaimsPage';
import { LiveOverviewPage } from './live/LiveOverviewPage';
import { LiveReleasesPage } from './live/LiveReleasesPage';
import {
  LiveDataQualityPage,
  LiveDiseaseMappingsPage,
  LiveFeatureMappingsPage,
  LiveRulesPage,
  LiveVocabularyLinksPage,
} from './live/screens';
import { ReviewEvaluationPage } from './ReviewEvaluationPage';
import { ReviewEvidencePage } from './ReviewEvidencePage';
import { ReviewDataQualityPage, ReviewDiseaseMappingsPage, ReviewFeatureMappingsPage } from './ReviewMappingsPage';
import { ReviewOverviewPage } from './ReviewOverviewPage';
import { ReviewReleasesPage } from './ReviewReleasesPage';
import { ReviewRulesPage } from './ReviewRulesPage';
import { ReviewShell } from './ReviewShell';

/**
 * Internal reviewer workspace routes (`/review/*`). Loaded as a separate chunk so the
 * audit fixtures and the dense review screens are not part of the patient-facing bundle.
 *
 * In http mode the screens read and write through the review API (M2.4a): what they show is
 * the stored data, and a note or decision is recorded by the service under the reviewer's
 * name. In mock mode they stay the design demo on fixtures, where nothing is recorded.
 */
export default function ReviewRoutes() {
  const { config } = useServices();
  if (config.serviceMode === 'http') {
    return (
      <Routes>
        <Route element={<ReviewShell />}>
          <Route index element={<LiveOverviewPage />} />
          <Route path="diseases" element={<LiveDiseaseMappingsPage />} />
          <Route path="features" element={<LiveFeatureMappingsPage />} />
          <Route path="data" element={<LiveDataQualityPage />} />
          <Route path="links" element={<LiveVocabularyLinksPage />} />
          <Route path="evidence" element={<LiveClaimsPage />} />
          <Route path="rules" element={<LiveRulesPage />} />
          <Route path="releases" element={<LiveReleasesPage />} />
          <Route path="*" element={<LiveOverviewPage />} />
        </Route>
      </Routes>
    );
  }
  return (
    <Routes>
      <Route element={<ReviewShell />}>
        <Route index element={<ReviewOverviewPage />} />
        <Route path="diseases" element={<ReviewDiseaseMappingsPage />} />
        <Route path="features" element={<ReviewFeatureMappingsPage />} />
        <Route path="evidence" element={<ReviewEvidencePage />} />
        <Route path="rules" element={<ReviewRulesPage />} />
        <Route path="releases" element={<ReviewReleasesPage />} />
        <Route path="data" element={<ReviewDataQualityPage />} />
        <Route path="evaluation" element={<ReviewEvaluationPage />} />
        <Route path="*" element={<ReviewOverviewPage />} />
      </Route>
    </Routes>
  );
}
