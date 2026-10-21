// The one-time token of a link in an email (/verify-email, /reset-password), F8.

type LinkWindow = {
  location: { href: string };
  history: { replaceState(state: unknown, unused: string, url: string): void };
};

/**
 * Takes `?token=` from the address and removes it at once, before anything is sent, so it
 * leaves no trace in the history, a bookmark or a Referer. Reloading then shows "expired".
 */
export function consumeLinkToken(win: LinkWindow): string | null {
  const url = new URL(win.location.href);
  const token = url.searchParams.get("token");
  if (!token) return null;
  win.history.replaceState(null, "", url.pathname);
  return token;
}

const pending = new Map<string, Promise<unknown>>();

/**
 * Sends a token once per page load. React runs effects twice in development (StrictMode); a
 * second POST of a one-time token would turn a good link into "expired".
 */
export function postOnce<Result>(token: string, post: () => Promise<Result>): Promise<Result> {
  let result = pending.get(token) as Promise<Result> | undefined;
  if (!result) {
    result = post();
    pending.set(token, result);
  }
  return result;
}
