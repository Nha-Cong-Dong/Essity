// The old /subjects/[id]/graph route checks the session, then redirects to /graph?subject=<id>.
import { redirect } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { Redirected, session } = vi.hoisted(() => ({
  Redirected: class extends Error {
    to: string;
    constructor(to: string) {
      super(to);
      this.to = to;
    }
  },
  session: vi.fn(),
}));
vi.mock("next/navigation", () => ({ redirect: (to: string) => { throw new Redirected(to); } }));
vi.mock("next/server", () => ({ connection: async () => {} }));
vi.mock("@/lib/session", () => ({ requireVerifiedSession: () => session() }));

const { default: Page } = await import("@/app/subjects/[id]/graph/page");

// The page wraps the redirecting child in Suspense; run the child directly.
const run = (id: string) => {
  const child = Page({ params: Promise.resolve({ id }) }) as {
    props: { children: { type: (p: unknown) => Promise<unknown>; props: unknown } };
  };
  const go = child.props.children;
  return go.type(go.props);
};

// Where the page redirected to (the mocked redirect and session both throw a Redirected).
const target = (id: string) => run(id).then(() => null, (error: Error) => error.message);

beforeEach(() => {
  session.mockReset();
});

describe("/subjects/[id]/graph", () => {
  it("signed out goes to /login, not to the graph", async () => {
    session.mockImplementation(async () => redirect("/login"));
    expect(await target("a")).toBe("/login");
  });
  it("signed in redirects to /graph?subject=<id>, encoded", async () => {
    session.mockResolvedValue({ email: "x@y.z" });
    expect(await target("a b/c")).toBe("/graph?subject=a%20b%2Fc");
  });
});
