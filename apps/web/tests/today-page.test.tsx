// Plan K16 wiring: /today hands the session's has_subjects to TodayNote. today-note.test.tsx
// pins the component; this pins the page that feeds it.
import { renderToReadableStream } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

let me: Record<string, unknown> = {};
vi.mock("@/lib/session", () => ({ requireVerifiedSession: async () => me }));
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

describe("/today follows has_subjects (plan K16)", () => {
  beforeEach(() => {
    me = { email: "a@example.com", email_verified: true };
  });

  // Red when: the page passes a constant (true or false) instead of me.has_subjects.
  it("has_subjects false: the invitation to create the first subject", async () => {
    me = { ...me, has_subjects: false };
    const markup = await html();
    expect(markup).toContain("Chưa có môn nào.");
    expect(markup).toContain('href="/subjects/new"');
  });

  it("has_subjects true: no 'no subject' sentence, a link to the subjects", async () => {
    me = { ...me, has_subjects: true };
    const markup = await html();
    expect(markup).not.toContain("Chưa có môn nào");
    expect(markup).toContain('href="/subjects"');
  });
});
