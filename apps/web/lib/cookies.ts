// Cookies web sets (ADR-0022). No imports, so proxy.ts can use it.

/**
 * The session cookie (ADR-0014, W6). `__Host-` makes the browser refuse it unless it is Secure,
 * on Path=/ and without Domain, so no subdomain can set or read it.
 */
export const SESSION_COOKIE = "__Host-essity_session";
/** The email just signed up with, for /check-email when there is no session yet (F1). */
export const PENDING_EMAIL_COOKIE = "__Host-essity_pending_email";

const COOKIE_ATTRIBUTES = {
  httpOnly: true,
  secure: true,
  sameSite: "lax",
  path: "/",
} as const;

/** Attributes for a cookie that ends at `expiresAt` (A2: core-api decides how long a session lives). */
export function cookieOptions(expiresAt: Date, now: Date = new Date()) {
  const maxAge = Math.max(0, Math.floor((expiresAt.getTime() - now.getTime()) / 1000));
  return { ...COOKIE_ATTRIBUTES, maxAge };
}

/** Attributes that delete a cookie: the browser only replaces a `__Host-` cookie set alike. */
export const EXPIRED_COOKIE = { ...COOKIE_ATTRIBUTES, maxAge: 0 };
