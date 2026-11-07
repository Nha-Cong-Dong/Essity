// T0.15: "/" shows the landing to a visitor without a session cookie and keeps today's redirect
// (landingFor) for anyone with one.
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

let cookieNames: string[] = [];
vi.mock("next/headers", () => ({
  cookies: async () => ({ has: (name: string) => cookieNames.includes(name) }),
}));
vi.mock("@/components/landing-redirect", () => ({
  LandingRedirect: () => "redirecting",
}));

const { LandingEntry } = await import("@/components/landing/landing-entry");
const { SESSION_COOKIE } = await import("@/lib/cookies");

const html = async () => renderToStaticMarkup(await LandingEntry());

describe("/ (T0.15)", () => {
  beforeEach(() => {
    cookieNames = [];
  });

  it("anonymous: the landing, with the approved words verbatim and the two ways in", async () => {
    const out = await html();
    expect(out).toContain("Hôm nay ôn gì,");
    expect(out).toContain("tôi lo!");
    expect(out).toContain("Trợ lí học tập tiên tiến. Quản lí lịch ôn luyện hiệu quả với thuật toán FSRS và đồ thị tri thức.");
    expect(out).toContain('href="/register"');
    expect(out).toContain('href="/login"');
    expect(out).not.toContain("redirecting");
  });

  it("with a session cookie: the redirect (the page asks core-api), not the landing", async () => {
    cookieNames = [SESSION_COOKIE];
    const out = await html();
    expect(out).toContain("redirecting");
    expect(out).not.toContain("Hôm nay ôn gì");
  });
});
