import type { ApiError } from '@/api/errors';

export interface ErrorCopy {
  title: string;
  message: string;
  /** Whether offering "Try again" makes sense. */
  canRetry: boolean;
}

/**
 * Patient-facing wording for a failed request. It describes what happened and what the
 * person can do; it never substitutes a medical guess for the missing result. The
 * service's own `message` is shown only for validation errors, where it explains what to fix.
 */
export function errorCopy(error: ApiError): ErrorCopy {
  switch (error.kind) {
    case 'network':
      return {
        title: 'You appear to be offline',
        message:
          'We couldn’t reach the service. Anything you typed is still here. Check your connection and try again.',
        canRetry: true,
      };
    case 'timeout':
      return {
        title: 'That took too long',
        message: 'The service didn’t respond in time. Nothing was lost. Please try again.',
        canRetry: true,
      };
    case 'rate_limited':
      return {
        title: 'Too many requests',
        message:
          error.retryAfterSeconds !== null
            ? `Please wait about ${Math.ceil(error.retryAfterSeconds)} seconds, then try again.`
            : 'Please wait a moment, then try again.',
        canRetry: true,
      };
    case 'unavailable':
      return {
        title: 'We couldn’t complete this assessment',
        message:
          'The assessment service is unavailable right now. No result has been produced. Your details are saved and you can try again.',
        canRetry: true,
      };
    case 'validation':
      return {
        title: 'That couldn’t be accepted',
        message: error.message || 'Something in that request wasn’t valid. Check it and try again.',
        canRetry: false,
      };
    case 'unauthenticated':
      return {
        title: 'Your session has ended',
        message: 'For your privacy the session was closed. Start a new symptom check to continue.',
        canRetry: false,
      };
    case 'forbidden':
      return {
        title: 'You don’t have access to this',
        message: 'This assessment belongs to a different session or account.',
        canRetry: false,
      };
    case 'not_found':
      return {
        title: 'We couldn’t find this assessment',
        message: 'It may have ended, been deleted or been reset.',
        canRetry: false,
      };
    case 'conflict':
      return {
        title: 'Your details changed',
        message: 'This assessment was updated elsewhere. Check your answer and send it again.',
        canRetry: true,
      };
    case 'in_progress':
      return {
        title: 'Still working on that',
        message: 'Your last request is still being processed. Nothing was lost. Wait a moment, then try again.',
        canRetry: true,
      };
    case 'idempotency_conflict':
      return {
        title: 'That request couldn’t be repeated',
        message: 'Please send it again.',
        canRetry: true,
      };
    case 'invalid_response':
      return {
        title: 'We couldn’t read the response',
        message: 'The service sent something unexpected, so nothing is shown rather than risk showing it wrongly.',
        canRetry: true,
      };
    case 'unexpected':
      return {
        title: 'Something went wrong',
        message: 'Nothing was lost. Please try again.',
        canRetry: error.retryable,
      };
  }
}

/** Reference shown with an error so support can find the request. Never contains health data. */
export function errorReference(error: ApiError): string | null {
  return error.requestId ? `Reference: ${error.requestId}` : null;
}
