import '@testing-library/jest-dom/vitest';

import { cleanup, configure } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// A wait for something to appear gives up after one second by default. The first test of a file renders the
// whole app, and on a busy machine that has taken longer (two tests failed so once in M3.12); three seconds
// keeps a slow start from reading as a missing element. A real absence still fails.
configure({ asyncUtilTimeout: 3000 });

// jsdom does not implement these browser APIs.
window.scrollTo = vi.fn();
if (!window.matchMedia) {
  window.matchMedia = vi.fn((query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn();
}
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = vi.fn();
  Element.prototype.releasePointerCapture = vi.fn();
}

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  window.sessionStorage.clear();
});
