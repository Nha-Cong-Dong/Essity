// T7.17 (US-02 AC1): the entry pages. Flag on: /sessions/new -> /sessions/study -> /sessions/[sid].
// Flag off (submission-drafts 404): study -> /sessions/new?v1=1, which shows v1 and does not bounce.
import { beforeEach, describe, expect, it, vi } from "vitest";

const SUBJECT = "9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b";
const SID = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";

class Redirected extends Error {
  constructor(readonly to: string) {
    super(to);
  }
}
const post = vi.fn();
vi.mock("next/navigation", () => ({ redirect: (to: string) => { throw new Redirected(to); } }));
vi.mock("next/server", () => ({ connection: async () => {} }));
vi.mock("next/headers", () => ({ cookies: async () => ({ get: () => ({ value: "t" }) }) }));
vi.mock("@/lib/session", () => ({ requireVerifiedSession: async () => {}, SESSION_COOKIE: "s" }));
vi.mock("@/components/subjects/subjects-loader", () => ({ subjectForUpload: async (id: string) => ({ id, name: "MMT" }) }));
vi.mock("@/lib/core-client", () => ({ coreClient: () => ({ POST: post }) }));
vi.mock("@/components/log-session", () => ({ LogSession: () => null }));

const { NewSessionEntry } = await import("@/components/session-study/new-entry");
const { StartStudy } = await import("@/components/session-study/start-study");

const to = async (run: () => Promise<unknown>) => {
  try {
    await run();
  } catch (error) {
    if (error instanceof Redirected) return error.to;
    throw error;
  }
  return null;
};
const entry = (query: { session?: string; v1?: string }) =>
  NewSessionEntry({ params: Promise.resolve({ id: SUBJECT }), searchParams: Promise.resolve(query) });
const start = () => StartStudy({ params: Promise.resolve({ id: SUBJECT }) });

beforeEach(() => post.mockReset());

describe("flag on", () => {
  it("/sessions/new redirects to the study start", async () => {
    expect(await to(() => entry({}))).toBe(`/subjects/${SUBJECT}/sessions/study`);
  });
  it("the study start opens a session and goes to its page", async () => {
    post.mockResolvedValue({ data: { session_id: SID }, response: { status: 201 } });
    expect(await to(start)).toBe(`/subjects/${SUBJECT}/sessions/${SID}`);
  });
});

describe("flag off", () => {
  it("submission-drafts 404 sends the learner to v1", async () => {
    post.mockResolvedValue({ data: undefined, response: { status: 404 } });
    expect(await to(start)).toBe(`/subjects/${SUBJECT}/sessions/new?v1=1`);
  });
  it("v1=1 shows the v1 page, no redirect loop", async () => {
    expect(await to(() => entry({ v1: "1" }))).toBeNull();
  });
});

it("another failure is still an error", async () => {
  post.mockResolvedValue({ data: undefined, response: { status: 500 } });
  await expect(start()).rejects.toThrow(/500/);
});
