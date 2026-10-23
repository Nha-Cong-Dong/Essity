// T1.22, PLAN "Xong khi": the baseline screen and its API are gone, so /onboarding and
// /api/baseline* answer 404 (no redirect: there were no production users, flow-expert 23/10b).
// Without a session cookie, proxy.ts sends /onboarding to /login like any other app page.
import { existsSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const APP = path.resolve(import.meta.dirname, "..", "app");

describe("removed routes stay gone (T1.22 plan E12)", () => {
  // Red when: the baseline page or its API is added back.
  it.each(["onboarding/page.tsx", "api/baseline/route.ts", "api/baseline/skip/route.ts"])("app/%s does not exist", (file) => {
    expect(existsSync(path.join(APP, file))).toBe(false);
  });

  it("the check looks where pages are", () => {
    expect(existsSync(path.join(APP, "today", "page.tsx"))).toBe(true);
  });
});
