// T1.18, plan K4: only the ways into the app send someone on; /today never does (it would loop
// right after "Nhập sau", since needs_baseline stays true until the second skip).
import { readFileSync } from "node:fs";
import path from "node:path";

import { beforeEach, describe, expect, it, vi } from "vitest";

let me: Record<string, unknown> | null = null;
vi.mock("@/lib/session", () => ({
  getSession: async () => me,
  requireVerifiedSession: async () => {
    if (me === null) throw new Error("redirect:/login");
    if (!me.email_verified) throw new Error("redirect:/check-email");
    return me;
  },
}));
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw new Error(`redirect:${to}`);
  },
}));
vi.mock("next/server", () => ({ connection: async () => undefined }));

const { LandingRedirect } = await import("@/components/landing-redirect");
const { RedirectIfSignedIn } = await import("@/components/auth/redirect-if-signed-in");
const { requireBaselineToEnter } = await import("@/lib/onboarding");

const ME = { email_verified: true, needs_baseline: true, has_subjects: false };

describe("entry points follow landingFor (plan K4)", () => {
  beforeEach(() => {
    me = { ...ME };
  });

  it.each([
    [{ needs_baseline: true }, "/onboarding"],
    [{ needs_baseline: false, has_subjects: false }, "/subjects/new"],
    [{ needs_baseline: false, has_subjects: true }, "/today"],
  ])("US-11 AC1, AC2: / with %j goes to %s", async (over, to) => {
    me = { ...ME, ...over };
    await expect(LandingRedirect()).rejects.toThrow(`redirect:${to}`);
  });

  it("/login while signed in goes where landingFor says", async () => {
    me = { ...ME, needs_baseline: false, has_subjects: false };
    await expect(RedirectIfSignedIn()).rejects.toThrow("redirect:/subjects/new");
  });

  it("/login while signed in but unverified goes to /check-email", async () => {
    me = { ...ME, email_verified: false };
    await expect(RedirectIfSignedIn()).rejects.toThrow("redirect:/check-email");
  });
});

describe("/onboarding guard (US-11 AC2)", () => {
  it("someone who needs a baseline stays", async () => {
    me = { ...ME };
    await expect(requireBaselineToEnter()).resolves.toEqual(ME);
  });

  // Red when: the guard goes, and someone with a baseline (or who skipped twice) can enter again.
  it.each([
    [{ needs_baseline: false, has_subjects: false }, "/subjects/new"],
    [{ needs_baseline: false, has_subjects: true }, "/today"],
  ])("with %j is sent to %s", async (over, to) => {
    me = { ...ME, ...over };
    await expect(requireBaselineToEnter()).rejects.toThrow(`redirect:${to}`);
  });
});

describe("/today stays put (plan K4)", () => {
  // Red when: /today starts sending people on (T2.14 must not add it back).
  it("app/today/page.tsx does not use landingFor or redirect", () => {
    const source = readFileSync(path.resolve(import.meta.dirname, "../app/today/page.tsx"), "utf-8");
    expect(source).not.toMatch(/landingFor|requireBaselineToEnter|\bredirect\(/);
  });
});
