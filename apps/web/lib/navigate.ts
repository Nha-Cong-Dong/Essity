/**
 * A full page load to `path`, so every server component reads the session afresh. One place, so
 * form tests replace it (jsdom cannot follow a navigation).
 */
export function go(path: string): void {
  window.location.assign(path);
}
