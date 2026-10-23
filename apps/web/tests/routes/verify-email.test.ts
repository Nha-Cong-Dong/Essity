import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "@/app/api/auth/verify-email/route";
import { PENDING_EMAIL_COOKIE, SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN, setCookies } from "../helpers";

const LINK_TOKEN = "link-token-marker-3c8d";
const ME = {
  id: "u1",
  email: "a@example.com",
  email_verified: true,
  timezone: "Asia/Ho_Chi_Minh",
  day_start_hour: 4,
  has_subjects: false,
};

/** `me` answers /v1/me in turn (the last one repeats): before the token is spent, then after. */
function core(verify: Response, me: Response | Response[] = Response.json(ME)) {
  const answers = Array.isArray(me) ? me : [me];
  let asked = 0;
  return fakeCoreApi((call) =>
    call.path === "/v1/me" ? answers[Math.min(asked++, answers.length - 1)].clone() : verify.clone(),
  );
}

const UNVERIFIED = { ...ME, email_verified: false };

describe("POST /api/auth/verify-email (T1.13)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it("sends the link's token to core-api in the body", async () => {
    const calls = core(Response.json({ status: "verified" }));

    await POST(browserPost("/api/auth/verify-email", { token: LINK_TOKEN }));

    expect(calls[0].path).toBe("/v1/auth/verify-email");
    expect(calls[0].body).toEqual({ token: LINK_TOKEN });
  });

  it("F4: without a session, says verified and not signed in", async () => {
    core(Response.json({ status: "verified" }));

    const response = await POST(browserPost("/api/auth/verify-email", { token: LINK_TOKEN }));

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ verified: true, signedIn: false });
  });

  it("F4: with the link owner's session, unverified before and verified after, says signed in", async () => {
    core(Response.json({ status: "verified" }), [Response.json(UNVERIFIED), Response.json(ME)]);

    const response = await POST(
      browserPost("/api/auth/verify-email", { token: LINK_TOKEN }, { cookies: { [SESSION_COOKIE]: "tok" } }),
    );

    expect(await response.json()).toEqual({ verified: true, signedIn: true, next: "/subjects/new" });
  });

  // Red when: the route names no page, or the wrong one, for the link owner (T1.22, decision A).
  it.each([
    [false, "/subjects/new"],
    [true, "/today"],
  ])("AC11: signed in with has_subjects %s → next %s", async (hasSubjects, next) => {
    core(Response.json({ status: "verified" }), [
      Response.json(UNVERIFIED),
      Response.json({ ...ME, has_subjects: hasSubjects }),
    ]);

    const response = await POST(
      browserPost("/api/auth/verify-email", { token: LINK_TOKEN }, { cookies: { [SESSION_COOKIE]: "tok" } }),
    );

    expect(await response.json()).toEqual({ verified: true, signedIn: true, next });
  });

  // Red when: /v1/me failing after the token is spent turns into 503, so "Thử lại" then says the
  // link expired, or the route names a page for a session it could not prove (T1.22 plan E4).
  it("AC11: /v1/me failing after verifying still says verified, not signed in, no next", async () => {
    let asked = 0;
    fakeCoreApi(async (call) => {
      if (call.path !== "/v1/me") return Response.json({ status: "verified" });
      if (asked++ === 0) return Response.json(UNVERIFIED);
      throw new TypeError("fetch failed");
    });

    const response = await POST(
      browserPost("/api/auth/verify-email", { token: LINK_TOKEN }, { cookies: { [SESSION_COOKIE]: "tok" } }),
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ verified: true, signedIn: false });
  });

  it("AC11: /v1/me answering 500 after verifying is the same: verified, not signed in", async () => {
    core(Response.json({ status: "verified" }), [
      Response.json(UNVERIFIED),
      Response.json({ detail: "boom" }, { status: 500 }),
    ]);

    const response = await POST(
      browserPost("/api/auth/verify-email", { token: LINK_TOKEN }, { cookies: { [SESSION_COOKIE]: "tok" } }),
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ verified: true, signedIn: false });
  });

  it("F4: someone else's session, verified all along, is not signed in (shared computer, review 822b3ea #2)", async () => {
    core(Response.json({ status: "verified" }), Response.json(ME));

    const response = await POST(
      browserPost("/api/auth/verify-email", { token: LINK_TOKEN }, { cookies: { [SESSION_COOKIE]: "tok" } }),
    );

    expect(await response.json()).toEqual({ verified: true, signedIn: false });
  });

  it("F4: a session whose account is still unverified is not signed in (another account's link)", async () => {
    core(Response.json({ status: "verified" }), Response.json({ ...ME, email_verified: false }));

    const response = await POST(
      browserPost("/api/auth/verify-email", { token: LINK_TOKEN }, { cookies: { [SESSION_COOKIE]: "tok" } }),
    );

    expect(await response.json()).toEqual({ verified: true, signedIn: false });
  });

  it("F1: forgets the pending sign-up email once verified", async () => {
    core(Response.json({ status: "verified" }));

    const response = await POST(
      browserPost(
        "/api/auth/verify-email",
        { token: LINK_TOKEN },
        { cookies: { [PENDING_EMAIL_COOKIE]: "a%40example.com" } },
      ),
    );

    expect(setCookies(response).get(PENDING_EMAIL_COOKIE)).toMatch(/Max-Age=0/i);
  });

  it.each([400, 422])(
    "AC2, F5: an expired, used or unknown link (%s) is one error, with whether a session exists",
    async (status) => {
      core(Response.json({ detail: "invalid_or_expired_token" }, { status }));

      const response = await POST(
        browserPost("/api/auth/verify-email", { token: LINK_TOKEN }, { cookies: { [SESSION_COOKIE]: "tok" } }),
      );

      expect(response.status).toBe(400);
      expect(await response.json()).toEqual({ error: "invalid_or_expired_token", signedIn: true });
    },
  );

  it("AC8: never echoes the link's token", async () => {
    core(Response.json({ detail: "invalid_or_expired_token" }, { status: 400 }));

    const response = await POST(browserPost("/api/auth/verify-email", { token: LINK_TOKEN }));

    expect(await response.text()).not.toContain(LINK_TOKEN);
  });

  it("ADR-0014: a POST from another site is refused before core-api is called", async () => {
    const calls = core(Response.json({ status: "verified" }));

    const response = await POST(
      browserPost("/api/auth/verify-email", { token: LINK_TOKEN }, { origin: "https://evil.example" }),
    );

    expect(response.status).toBe(403);
    expect(calls).toHaveLength(0);
  });
});
