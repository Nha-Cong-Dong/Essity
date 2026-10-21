// Sáng / Tối / Theo hệ thống (DESIGN.md §3.6, §5). The OS decides unless <html data-theme>
// says otherwise (app/globals.css); the choice is remembered in this browser only.

export type Theme = "light" | "dark" | "system";

export const THEME_KEY = "essity-theme";

type Storage = Pick<globalThis.Storage, "getItem" | "setItem" | "removeItem">;
type Root = { dataset: Record<string, string | undefined> };

/**
 * The browser's localStorage, or null when site data is blocked: then even reading
 * window.localStorage throws a SecurityError (review 5c04bae #1).
 */
export function browserStorage(reach: () => Storage = () => window.localStorage): Storage | null {
  try {
    return reach();
  } catch {
    return null;
  }
}

export function readTheme(storage: Storage | null): Theme {
  try {
    const value = storage?.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system"; // storage blocked (private window): follow the OS
  }
}

export function saveTheme(theme: Theme, storage: Storage | null): void {
  try {
    if (theme === "system") storage?.removeItem(THEME_KEY);
    else storage?.setItem(THEME_KEY, theme);
  } catch {
    // Not remembered; the choice still holds for this page.
  }
}

export function applyTheme(theme: Theme, root: Root): void {
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;
}

/** What the account menu does on a pick: the page changes now, the browser remembers it. */
export function chooseTheme(theme: Theme, storage: Storage | null, root: Root): void {
  applyTheme(theme, root);
  saveTheme(theme, storage);
}

/**
 * Run in <head> before the page paints, so a chosen theme never flashes the OS one first.
 * Plain ES5, no imports: it is inlined as text. Only the two known values are ever written.
 * There is no CSP yet; a strict script-src would need a nonce on this tag.
 */
export const THEME_SCRIPT = `try{var t=localStorage.getItem(${JSON.stringify(THEME_KEY)});if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;
