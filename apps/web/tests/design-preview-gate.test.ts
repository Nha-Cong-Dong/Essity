// Edge cases of the /design-preview gate (plan V11, V14) that proxy.test.ts leaves open.
import { NextRequest } from "next/server";
import { describe, expect, it, vi } from "vitest";

import { SESSION_COOKIE } from "@/lib/cookies";
import { designPreviewAllowed, isDesignPreview } from "@/lib/design-preview";
import { config, proxy } from "@/proxy";

import { ORIGIN } from "./helpers";

const status = (path: string, cookie?: string) =>
  proxy(new NextRequest(`${ORIGIN}${path}`, { headers: cookie ? { cookie: `${SESSION_COOKIE}=${cookie}` } : {} })).status;

describe("/design-preview gate: edges", () => {
  // Red when: isDesignPreview stops matching below the page (`startsWith` dropped or narrowed):
  // a nested route would skip the gate and reach core-api through ServiceChain-like children.
  it.each(["/design-preview/x", "/design-preview/a/b", "/design-preview//", "/design-preview/subjects", "/design-preview/today", "/design-preview/today-v1", "/design-preview/subject", "/design-preview/subject-live"])("%s is closed in production", (path) => {
    vi.stubEnv("NODE_ENV", "production");
    expect(status(path, "tok")).toBe(404);
    expect(status(path)).toBe(404);
  });

  // Red when: the proxy matcher is edited to skip this path: the gate would never run.
  it("the matcher runs the proxy on the page and below it", () => {
    const runs = (path: string) => new RegExp(`^${config.matcher[0]}$`).test(path);
    expect(runs("/design-preview")).toBe(true);
    expect(runs("/design-preview/")).toBe(true);
    expect(runs("/design-preview/x")).toBe(true);
  });

  // Red when: the match turns into a loose prefix test that swallows other pages, or a case
  // variant starts to count as the page (Next routes are case-sensitive, so it is a plain 404).
  it("look-alike paths are not the page", () => {
    expect(isDesignPreview("/design-previews")).toBe(false);
    expect(isDesignPreview("/design-preview-x")).toBe(false);
    expect(isDesignPreview("/x/design-preview")).toBe(false);
    expect(isDesignPreview("/design-preview")).toBe(true);
    expect(isDesignPreview("/design-preview/")).toBe(true);
  });

  // Red when: the allowed test falls back to a truthy check or to NODE_ENV !== "production".
  it.each([
    [{ NODE_ENV: "production", WEB_DESIGN_PREVIEW: "1" }, true],
    [{ NODE_ENV: "development" }, true],
    [{ NODE_ENV: "development", WEB_DESIGN_PREVIEW: "0" }, true],
    [{ NODE_ENV: "production", WEB_DESIGN_PREVIEW: "01" }, false],
    [{ NODE_ENV: "production", WEB_DESIGN_PREVIEW: "1 " }, false],
    [{ NODE_ENV: "Development" }, false],
    [{ NODE_ENV: "production" }, false],
    [{ NODE_ENV: "staging" }, false],
    [{}, false],
  ])("designPreviewAllowed(%j) = %s", (env, expected) => {
    expect(designPreviewAllowed(env)).toBe(expected);
  });

  // Red when: the proxy reads the environment once at import time instead of on every request.
  it("is read on every request, not frozen at import", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("WEB_DESIGN_PREVIEW", "1");
    expect(status("/design-preview")).toBe(200);
    vi.stubEnv("WEB_DESIGN_PREVIEW", "");
    expect(status("/design-preview")).toBe(404);
  });

  // Red when: a closed page answers with a redirect to /login or a body that tells it exists.
  it("a closed page is an empty 404, not a redirect", () => {
    vi.stubEnv("NODE_ENV", "production");
    const response = proxy(new NextRequest(`${ORIGIN}/design-preview`));
    expect(response.status).toBe(404);
    expect(response.headers.get("location")).toBeNull();
  });
});
