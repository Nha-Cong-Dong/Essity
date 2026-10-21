import { isIP } from "node:net";

/**
 * The user's IP, as appended to X-Forwarded-For by the `trustedProxyHops`-th proxy counting
 * back from web (W4). Entries further left were written by the client and prove nothing.
 * Null when no proxy is trusted or the entry is missing or malformed; core-api then uses the
 * address it sees.
 */
export function clientIpFrom(headers: Headers, trustedProxyHops: number): string | null {
  if (trustedProxyHops === 0) return null;
  const entries = (headers.get("x-forwarded-for") ?? "").split(",").map((entry) => entry.trim());
  const candidate = entries.at(-trustedProxyHops);
  if (entries.length < trustedProxyHops || candidate === undefined) return null;
  return isIP(candidate) ? candidate : null;
}
