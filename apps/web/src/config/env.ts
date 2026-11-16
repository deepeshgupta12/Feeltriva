/**
 * Public build configuration. Everything read here is compiled into the browser bundle,
 * so it must never contain secrets.
 */
export type ServiceMode = 'mock' | 'http';

export interface AppConfig {
  serviceMode: ServiceMode;
  apiBaseUrl: string;
  devAuth: boolean;
  demoTools: boolean;
}

export interface RawEnv {
  VITE_SERVICE_MODE?: string;
  VITE_API_BASE_URL?: string;
  VITE_DEV_AUTH?: string;
  VITE_DEMO_TOOLS?: string;
  DEV?: boolean;
}

export const DEFAULT_API_BASE_URL = 'http://localhost:8000';

export function parseConfig(env: RawEnv): AppConfig {
  const serviceMode: ServiceMode = env.VITE_SERVICE_MODE === 'http' ? 'http' : 'mock';
  const apiBaseUrl = (env.VITE_API_BASE_URL?.trim() || DEFAULT_API_BASE_URL).replace(/\/+$/, '');
  const devAuth = env.VITE_DEV_AUTH === 'true';

  let demoTools = serviceMode === 'mock' || env.DEV === true;
  if (env.VITE_DEMO_TOOLS === 'true') {
    demoTools = true;
  } else if (env.VITE_DEMO_TOOLS === 'false') {
    demoTools = false;
  }

  return { serviceMode, apiBaseUrl, devAuth, demoTools };
}

export const appConfig: AppConfig = parseConfig(import.meta.env);
