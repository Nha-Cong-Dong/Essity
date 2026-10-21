import { describe, expect, it } from "vitest";

import { applyTheme, browserStorage, chooseTheme, readTheme, saveTheme, THEME_KEY, THEME_SCRIPT } from "@/lib/theme";

function fakeRoot() {
  return { dataset: {} as Record<string, string | undefined> };
}

function fakeStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
  };
}

const broken = {
  getItem: () => {
    throw new Error("blocked");
  },
  setItem: () => {
    throw new Error("blocked");
  },
  removeItem: () => {
    throw new Error("blocked");
  },
};

describe("theme (DESIGN.md §3.6, §5: Sáng / Tối / Theo hệ thống)", () => {
  it("follows the system until a choice is made", () => {
    expect(readTheme(fakeStorage())).toBe("system");
  });

  it("remembers a choice", () => {
    const storage = fakeStorage();
    saveTheme("dark", storage);
    expect(readTheme(storage)).toBe("dark");
    saveTheme("system", storage);
    expect(storage.data.has(THEME_KEY)).toBe(false);
  });

  it("ignores a stored value it does not know", () => {
    expect(readTheme(fakeStorage({ [THEME_KEY]: "sepia" }))).toBe("system");
  });

  it("still works when storage is blocked (private window)", () => {
    expect(readTheme(broken)).toBe("system");
    expect(() => saveTheme("dark", broken)).not.toThrow();
  });

  it("sets <html data-theme> for a choice and removes it for the system", () => {
    const root = fakeRoot();
    applyTheme("light", root);
    expect(root.dataset.theme).toBe("light");
    applyTheme("system", root);
    expect(root.dataset.theme).toBeUndefined();
  });

  it("choosing in the account menu applies the theme at once and remembers it", () => {
    const storage = fakeStorage();
    const root = fakeRoot();
    chooseTheme("dark", storage, root);
    expect(root.dataset.theme).toBe("dark");
    expect(readTheme(storage)).toBe("dark");
    chooseTheme("system", storage, root);
    expect(root.dataset.theme).toBeUndefined();
    expect(storage.data.has(THEME_KEY)).toBe(false);
  });

  it("a choice still applies to the page when storage is blocked", () => {
    const root = fakeRoot();
    chooseTheme("light", broken, root);
    expect(root.dataset.theme).toBe("light");
  });

  it("site data blocked: reaching localStorage itself throws, the menu still works (review 5c04bae #1)", () => {
    const storage = browserStorage(() => {
      throw new DOMException("The operation is insecure.", "SecurityError");
    });
    expect(storage).toBeNull();
    expect(readTheme(storage)).toBe("system");
    const root = fakeRoot();
    expect(() => chooseTheme("dark", storage, root)).not.toThrow();
    expect(root.dataset.theme).toBe("dark");
  });

  it("browserStorage gives the storage when it can be reached", () => {
    const storage = fakeStorage();
    expect(browserStorage(() => storage)).toBe(storage);
  });

  it("the inline script applies the stored choice before the page paints", () => {
    const root = fakeRoot();
    new Function("localStorage", "document", THEME_SCRIPT)(fakeStorage({ [THEME_KEY]: "dark" }), {
      documentElement: root,
    });
    expect(root.dataset.theme).toBe("dark");
  });

  it("the inline script never throws, and never writes what it does not know", () => {
    const root = fakeRoot();
    const run = (storage: unknown) =>
      new Function("localStorage", "document", THEME_SCRIPT)(storage, { documentElement: root });
    expect(() => run(broken)).not.toThrow();
    run(fakeStorage({ [THEME_KEY]: "<script>" }));
    expect(root.dataset.theme).toBeUndefined();
  });
});
