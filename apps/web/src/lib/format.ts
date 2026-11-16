const dateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: 'long' });
const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
});
const numberFormatter = new Intl.NumberFormat('en-US');

export function formatDate(date: Date): string {
  return dateFormatter.format(date);
}

export function formatDateTime(date: Date): string {
  return dateTimeFormatter.format(date);
}

export function formatCount(value: number): string {
  return numberFormatter.format(value);
}

/**
 * Turns an opaque identifier into readable words without adding meaning:
 * "fx.signal_alpha" -> "Signal alpha".
 */
export function humanizeIdentifier(identifier: string): string {
  const lastSegment = identifier.split(/[.:/]/).filter(Boolean).pop() ?? identifier;
  const words = lastSegment.replace(/[_-]+/g, ' ').trim();
  if (words.length === 0) {
    return identifier;
  }
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Only http(s) links from the service are rendered as links. */
export function safeExternalUrl(url: string | null | undefined): string | null {
  if (!url) {
    return null;
  }
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.toString() : null;
  } catch {
    return null;
  }
}
