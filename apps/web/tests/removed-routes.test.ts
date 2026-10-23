// T1.22, PLAN "Xong khi": the baseline screen and its API are gone, so /onboarding and
// /api/baseline* answer 404 (no redirect: there were no production users, flow-expert 23/10b).
// Without a session cookie, proxy.ts sends /onboarding to /login like any other app page.
import { describe, expect, it } from "vitest";

import { appRoutes } from "./app-routes";

const URLS = [...appRoutes("page"), ...appRoutes("route")].map((segments) => `/${segments.join("/")}`);

/** The removed URLs among `urls`. */
export function removed(urls: string[]): string[] {
  return urls.filter((url) => url === "/onboarding" || url === "/api/baseline" || url.startsWith("/api/baseline/"));
}

describe("removed routes stay gone (T1.22 plan E12)", () => {
  // Red when: the baseline page or its API is added back, under any file kind or route group.
  it("no page or route answers /onboarding or /api/baseline*", () => {
    expect(removed(URLS)).toEqual([]);
  });

  it("the check sees the app's pages and routes", () => {
    expect(URLS).toContain("/today");
    expect(URLS).toContain("/api/auth/verify-email");
  });

  // Red when: the check misses a way the page could come back (review b398bd3 #2).
  it("catches /onboarding and /api/baseline/skip", () => {
    expect(removed(["/onboarding", "/api/baseline", "/api/baseline/skip", "/today", "/api/baselines"])).toEqual([
      "/onboarding",
      "/api/baseline",
      "/api/baseline/skip",
    ]);
  });
});
