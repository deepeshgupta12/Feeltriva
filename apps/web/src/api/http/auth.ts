import { uuid } from '@/lib/uuid';

/**
 * Supplies the bearer token for API requests. Returning `null` sends no Authorization
 * header; the API then answers 401 and the UI shows its signed-out state.
 */
export type AuthTokenProvider = () => string | null | Promise<string | null>;

/**
 * Local development auth (`VITE_DEV_AUTH=true`).
 *
 * The subject is a random UUID created once per page load and held only in this closure:
 * it is anonymous, is not an account, is never written to browser storage and is gone on
 * reload. The backend accepts `Bearer dev:<subject>` only when its own dev-auth switch is on.
 */
export function createDevAuthTokenProvider(subject: string = uuid()): AuthTokenProvider {
  const token = `dev:${subject}`;
  return () => token;
}

/**
 * TODO(auth): real authentication boundary.
 *
 * Production needs a token provider backed by the product's identity provider (for example
 * an OIDC session that yields a short-lived JWT for the API audience). That integration
 * does not exist yet and is deliberately not faked here. Until it does, non-dev builds send
 * no Authorization header, so a protected API responds 401 and nothing private is rendered.
 *
 * Replace this function; `HttpAssessmentService` needs no other change.
 */
export function createUnconfiguredAuthTokenProvider(): AuthTokenProvider {
  return () => null;
}

export function createAuthTokenProvider(options: { devAuth: boolean }): AuthTokenProvider {
  return options.devAuth ? createDevAuthTokenProvider() : createUnconfiguredAuthTokenProvider();
}
