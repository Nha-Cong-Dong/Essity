// /design-preview is the page for checking the design system by eye. It renders ServiceChain,
// which calls core-api on every request, so outside development it stays closed unless
// WEB_DESIGN_PREVIEW is exactly "1" (plan design-tokens-v3 V11, V14). Read on every request in
// proxy.ts, which answers 404. The page checks again after connection() (a value read at build
// time could freeze with cacheComponents), but inside Suspense: that second lock only stops the
// core-api call, the page itself has already started with 200.

export const DESIGN_PREVIEW_PATH = "/design-preview";

export function designPreviewAllowed(env: Record<string, string | undefined>): boolean {
  return env.NODE_ENV === "development" || env.WEB_DESIGN_PREVIEW === "1";
}

/**
 * Whether a request path reaches the preview. Compared after decoding (`/design%2Dpreview`) and
 * collapsing repeated slashes (`//design-preview`), since the router may do both; a path that
 * cannot be decoded counts as the preview, so the gate fails closed.
 */
export function isDesignPreview(pathname: string): boolean {
  let path: string;
  try {
    path = decodeURIComponent(pathname);
  } catch {
    return true;
  }
  path = path.replace(/\/{2,}/g, "/").toLowerCase();
  return path === DESIGN_PREVIEW_PATH || path.startsWith(`${DESIGN_PREVIEW_PATH}/`);
}
