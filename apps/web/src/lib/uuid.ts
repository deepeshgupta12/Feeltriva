/**
 * RFC 4122 v4 UUID. `crypto.randomUUID` only exists in secure contexts, so fall back to
 * `getRandomValues` (available everywhere we support) instead of Math.random.
 */
export function uuid(): string {
  const c = globalThis.crypto;
  if (typeof c.randomUUID === 'function') {
    return c.randomUUID();
  }
  const bytes = c.getRandomValues(new Uint8Array(16));
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0'));
  return [
    hex.slice(0, 4).join(''),
    hex.slice(4, 6).join(''),
    hex.slice(6, 8).join(''),
    hex.slice(8, 10).join(''),
    hex.slice(10, 16).join(''),
  ].join('-');
}
