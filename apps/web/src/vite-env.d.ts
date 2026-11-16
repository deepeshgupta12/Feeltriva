/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SERVICE_MODE?: string;
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_DEV_AUTH?: string;
  readonly VITE_DEMO_TOOLS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
