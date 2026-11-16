import { Route, Routes } from 'react-router';

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
 */
export default function ReviewRoutes() {
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
