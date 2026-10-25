// T2.14: /today feeds GET /v1/today to TodayScreen. today-screen.test.tsx pins the screen; this
// pins the page: the session is checked first, and a failing /v1/today is a notice, not a guess
// and never a redirect (DESIGN.md §6.3, plan K4).
import { renderToReadableStream } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const me = { email: "a@example.com", email_verified: true, has_subjects: true };
let today: () => Promise<unknown>;
vi.mock("@/lib/session", () => ({ requireVerifiedSession: async () => me }));
vi.mock("@/lib/today", () => ({ getToday: () => today() }));
vi.mock("next/server", () => ({ connection: async () => undefined }));
vi.mock("@/components/account-menu", () => ({ AccountMenu: () => null }));
vi.mock("@/components/shells", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
}));

const { default: TodayPage } = await import("@/app/today/page");

async function html(): Promise<string> {
  const stream = await renderToReadableStream(<TodayPage />);
  await stream.allReady;
  return new Response(stream).text();
}

describe("/today page (T2.14)", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  // Red when: the page ignores /v1/today (a constant screen) or drops its state.
  it("draws what /v1/today answers", async () => {
    today = async () => ({
      learning_day: "2026-10-21",
      state: "rested",
      session: null,
      in_progress: null,
      backlog: null,
      next_day: "2026-10-22",
      subjects: [],
    });
    const markup = await html();
    expect(markup).toContain("Hôm nay không cần ôn.");
    expect(markup).toContain("thứ Năm, 22/10");
  });

  // Red when: a failing /v1/today throws to the error page or shows a made-up state.
  it("a failing /v1/today is the notice with Thử lại", async () => {
    today = async () => {
      throw new Error("core-api answered /v1/today with 500");
    };
    const markup = await html();
    expect(markup).toContain('role="alert"');
    expect(markup).toContain("Không tải được phiên hôm nay.");
    expect(markup).toContain("Thử lại");
    expect(markup).not.toContain("Hôm nay không cần ôn");
  });
});
