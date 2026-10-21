// /design-preview is the page for checking the design system by eye. It renders ServiceChain,
// which calls core-api on every request, so outside development it stays closed unless
// WEB_DESIGN_PREVIEW is exactly "1" (plan design-tokens-v3 V11, V14). Read on every request in
// proxy.ts, never in the page: with cacheComponents a page could freeze the answer at build time.

export const DESIGN_PREVIEW_PATH = "/design-preview";

export function designPreviewAllowed(env: Record<string, string | undefined>): boolean {
  return env.NODE_ENV === "development" || env.WEB_DESIGN_PREVIEW === "1";
}

export function isDesignPreview(pathname: string): boolean {
  return pathname === DESIGN_PREVIEW_PATH || pathname.startsWith(`${DESIGN_PREVIEW_PATH}/`);
}
