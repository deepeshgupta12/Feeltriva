import js from '@eslint/js';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist', 'coverage', 'node_modules', 'src/api/generated/**', 'src/fixtures/*.generated.ts'] },
  {
    files: ['src/**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommendedTypeChecked,
      jsxA11y.flatConfigs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // Option rows wrap the control and its text in nested spans.
      'jsx-a11y/label-has-associated-control': ['error', { assert: 'either', depth: 4 }],
      '@typescript-eslint/consistent-type-imports': ['error', { fixStyle: 'inline-type-imports' }],
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      // Health data must never reach persistent browser storage. The single allowed use is
      // the non-sensitive preference store, which disables this rule locally.
      'no-restricted-globals': [
        'error',
        {
          name: 'localStorage',
          message: 'Do not persist data. See src/state/preferences.ts for the only allowed use.',
        },
        { name: 'sessionStorage', message: 'Do not persist data in the browser.' },
        { name: 'indexedDB', message: 'Do not persist data in the browser.' },
        { name: 'caches', message: 'Do not cache responses: they can contain health data.' },
      ],
      'no-restricted-properties': [
        'error',
        { object: 'window', property: 'localStorage', message: 'Do not persist data. See src/state/preferences.ts.' },
        { object: 'window', property: 'sessionStorage', message: 'Do not persist data in the browser.' },
        { object: 'window', property: 'indexedDB', message: 'Do not persist data in the browser.' },
        {
          object: 'globalThis',
          property: 'localStorage',
          message: 'Do not persist data. See src/state/preferences.ts.',
        },
        { object: 'globalThis', property: 'sessionStorage', message: 'Do not persist data in the browser.' },
        { object: 'globalThis', property: 'indexedDB', message: 'Do not persist data in the browser.' },
      ],
    },
  },
  {
    // The one sanctioned storage access: non-sensitive UI preferences.
    files: ['src/state/preferences.ts'],
    rules: { 'no-restricted-properties': 'off', 'no-restricted-globals': 'off' },
  },
  {
    files: ['src/**/*.test.{ts,tsx}', 'src/test/**'],
    rules: {
      'no-restricted-properties': 'off',
      'no-restricted-globals': 'off',
      '@typescript-eslint/unbound-method': 'off',
    },
  },
  {
    files: ['*.config.{js,ts}', 'scripts/**/*.mjs'],
    extends: [js.configs.recommended],
    languageOptions: { ecmaVersion: 2023, globals: globals.node },
  },
  {
    // The smoke test passes callbacks to the browser (page.evaluate), so it sees both worlds.
    files: ['scripts/smoke.mjs'],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
  },
);
