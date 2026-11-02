// T9.3 (US-18 AC1, AC3, AC4, AC8): the two routes behind the command bar.
import { beforeEach, describe, expect, it, vi } from "vitest";

import { POST as undo } from "@/app/api/commands/[id]/undo/route";
import { POST as apply } from "@/app/api/commands/route";
import { SESSION_COOKIE } from "@/lib/session";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "../helpers";

const TOKEN = "session-token-marker-commands";
const SIGNED_IN = { cookies: { [SESSION_COOKIE]: TOKEN } };
const CMD = "11111111-2222-4333-8444-555555555555";
const SCREEN = "21111111-2222-4333-8444-555555555555";
const SUBJECT = "31111111-2222-4333-8444-555555555555";
const body = { command_id: CMD, screen_session_id: SCREEN, subject_id: SUBJECT, text: "mục 3.4 kết thúc ở trang 80" };
const params = (id = CMD) => ({ params: Promise.resolve({ id }) });
const refusal = (status: number, detail: unknown) => Response.json({ detail }, { status });

describe("command routes (T9.3)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });

  it("US-18 AC1: POST passes the four fields and the session on and answers the diff", async () => {
    const out = { status: "applied", diff: [], affected: 1, op_kinds: ["section_set_pages"] };
    const calls = fakeCoreApi(() => Response.json(out));
    const response = await apply(browserPost("/api/commands", body, SIGNED_IN));
    expect(calls[0].path).toBe("/v1/commands");
    expect(calls[0].body).toEqual(body);
    expect(calls[0].headers.get("authorization")).toBe(`Bearer ${TOKEN}`);
    expect(await response.json()).toEqual(out);
  });

  it("US-18 AC1: POST refuses extra keys (ops), a bad id or no session without a call", async () => {
    const calls = fakeCoreApi(() => Response.json({}));
    const statuses = [
      (await apply(browserPost("/x", { ...body, ops: [{ kind: "card_edit" }] }, SIGNED_IN))).status,
      (await apply(browserPost("/x", { ...body, command_id: "../x" }, SIGNED_IN))).status,
      (await apply(browserPost("/x", { ...body, text: 5 }, SIGNED_IN))).status,
      (await apply(browserPost("/x", body, { cookies: {} }))).status,
      (await apply(browserPost("/x", body, { ...SIGNED_IN, origin: "https://evil.example" }))).status,
    ];
    expect(statuses).toEqual([400, 400, 400, 401, 403]);
    expect(calls).toHaveLength(0);
  });

  it("US-18 AC3: an unclear answer is passed on as it is", async () => {
    fakeCoreApi(() => Response.json({ status: "unclear", reason: "ambiguous" }));
    const response = await apply(browserPost("/x", body, SIGNED_IN));
    expect(await response.json()).toEqual({ status: "unclear", reason: "ambiguous" });
  });

  // Red when: the budget code is lost, so the bar cannot tell "turn off" from "slow down".
  it("US-18 AC8: 429 quota_hard_cap keeps its code, another 429 is the rate limit", async () => {
    fakeCoreApi(() => refusal(429, "quota_hard_cap"));
    const spent = await apply(browserPost("/x", body, SIGNED_IN));
    expect([spent.status, await spent.json()]).toEqual([429, { error: "quota_hard_cap" }]);
    fakeCoreApi(() => Response.json({}, { status: 429, headers: { "retry-after": "7" } }));
    const limited = await apply(browserPost("/x", body, SIGNED_IN));
    expect([limited.status, await limited.json(), limited.headers.get("retry-after")]).toEqual([
      429,
      { error: "rate_limited" },
      "7",
    ]);
  });

  it.each([
    [409, "command_id_reused"],
    [409, "changed_after"],
    [409, "not_latest"],
    [404, "not_owned"],
    [422, "unsupported"],
    [503, "parse_unavailable"],
    [502, "parse_invalid"],
  ])("US-18 AC4: %s %s is passed on as its code", async (status, detail) => {
    fakeCoreApi(() => refusal(status, detail));
    const response = await apply(browserPost("/x", body, SIGNED_IN));
    expect([response.status, await response.json()]).toEqual([status, { error: detail }]);
  });

  it("US-18 AC4: a code web does not know, or a validation list, never reaches the browser as text", async () => {
    fakeCoreApi(() => refusal(422, "some text of the command"));
    expect(await (await apply(browserPost("/x", body, SIGNED_IN))).json()).toEqual({ error: "rejected" });
    fakeCoreApi(() => refusal(422, [{ msg: "text of the command" }]));
    expect(await (await apply(browserPost("/x", body, SIGNED_IN))).json()).toEqual({ error: "invalid_request" });
  });

  it("US-18 AC4: core-api down is 503 unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Promise.reject(new TypeError("down"))),
    );
    const response = await apply(browserPost("/x", body, SIGNED_IN));
    expect([response.status, await response.json()]).toEqual([503, { error: "unavailable" }]);
  });

  it("US-18 AC4: undo posts to the command's own path and passes 409 not_latest on", async () => {
    const calls = fakeCoreApi(() => Response.json({ status: "undone", diff: [], affected: 1, replayed: false }));
    expect((await undo(browserPost("/x", undefined, SIGNED_IN), params())).status).toBe(200);
    expect([calls[0].path, calls[0].method]).toEqual([`/v1/commands/${CMD}/undo`, "POST"]);
    fakeCoreApi(() => refusal(409, "not_latest"));
    const late = await undo(browserPost("/x", undefined, SIGNED_IN), params());
    expect([late.status, await late.json()]).toEqual([409, { error: "not_latest" }]);
  });

  it("US-18 AC4: undo refuses a bad id or no session without a call", async () => {
    const calls = fakeCoreApi(() => Response.json({}));
    expect((await undo(browserPost("/x", undefined, SIGNED_IN), params("../x"))).status).toBe(400);
    expect((await undo(browserPost("/x", undefined, { cookies: {} }), params())).status).toBe(401);
    expect(calls).toHaveLength(0);
  });
});
