import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';

// Self-hosted fonts (no external font CDN requests).
import '@fontsource/inter/latin-400.css';
import '@fontsource/inter/latin-500.css';
import '@fontsource/inter/latin-600.css';
import '@fontsource/manrope/latin-600.css';
import '@fontsource/manrope/latin-700.css';
import './index.css';

import { App } from './App';
import { AppProviders } from './state/AppProviders';

const container = document.getElementById('root');
if (!container) {
  throw new Error('Root element #root is missing from index.html.');
}

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <AppProviders>
        <App />
      </AppProviders>
    </BrowserRouter>
  </StrictMode>,
);
