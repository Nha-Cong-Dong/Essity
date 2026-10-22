// Risk register R24 wiring: the pages compute the example from the session's learning day and
// hand it to the forms (exam-example.test.ts pins the arithmetic, subject-screens the fields).
import { renderToReadableStream } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const me = {
  email: "a@example.com",
  email_verified: true,
  timezone: "Asia/Ho_Chi_Minh",
  day_start_hour: 4,
};
vi.mock("@/lib/session", () => ({ requireVerifiedSession: async () => me }));
vi.mock("next/server", () => ({ connection: async () => undefined }));
vi.mock("@/components/account-slot", () => ({ AccountSlot: () => null }));
vi.mock("@/components/shells", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
}));
const handed: unknown[] = [];
vi.mock("@/components/subjects/subjects-loader", () => ({
  Subjects: (props: { example: string }) => {
    handed.push(props.example);
    return null;
  },
}));

const { default: NewSubjectPage } = await import("@/app/subjects/new/page");
const { default: SubjectsPage } = await import("@/app/subjects/page");

async function html(node: React.ReactNode): Promise<string> {
  const stream = await renderToReadableStream(node);
  await stream.allReady;
  return new Response(stream).text();
}

describe("the pages pass the user's example (R24)", () => {
  beforeEach(() => {
    // 15/12 05:00 in Ho Chi Minh City: an exam on 15/12 this year is already refused.
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-12-14T22:00:00Z"));
  });
  afterEach(() => vi.useRealTimers());

  // Red when: /subjects/new uses a fixed example or the server's (UTC) date.
  it("/subjects/new", async () => {
    expect(await html(<NewSubjectPage />)).toContain('placeholder="15/12/2027"');
  });

  // Red when: the list page hands no example (or a fixed one) to the edit forms.
  it("/subjects hands the same example to its list", async () => {
    await html(<SubjectsPage />);
    expect(handed).toEqual(["15/12/2027"]);
  });
});
