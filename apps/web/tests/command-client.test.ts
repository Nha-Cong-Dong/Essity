// T9.3 (US-18 AC1, AC3, AC4, AC8): the browser adapter of the command bar.
import { afterEach, describe, expect, it, vi } from "vitest";

import { diffOf, liveCommands } from "@/lib/command-client";

const CMD = { id: "11111111-2222-4333-8444-555555555555", text: "phần 3.4 kết thúc ở trang 80" };
const signal = new AbortController().signal;

function reply(status: number, json: unknown) {
  const fn = vi.fn<typeof fetch>(async () => Response.json(json, { status }));
  vi.stubGlobal("fetch", fn);
  return fn;
}
function setup() {
  const changed = vi.fn();
  const signedOut = vi.fn();
  return { changed, signedOut, ...liveCommands({ subjectId: "s", screenSessionId: "x", changed, signedOut }) };
}
const applied = (extra: object = {}) => ({
  status: "applied" as const,
  affected: 1,
  op_kinds: ["section_set_pages"],
  diff: [{ kind: "doc_section", id: "i", verb: "changed", before: null, after: null }],
  ...extra,
});

afterEach(() => vi.unstubAllGlobals());

describe("diffOf", () => {
  it("US-18 AC4: the words come from the op kind, the count from `affected`", () => {
    expect(diffOf(applied({ op_kinds: ["section_exclude"], affected: 12 }))).toMatchObject({
      verb: "bỏ",
      noun: "phần",
      count: 12,
    });
  });
  it("US-18 AC4: one changed card shows the old and the new text", () => {
    const diff = diffOf(
      applied({
        op_kinds: ["card_edit"],
        diff: [{ kind: "unit", id: "i", verb: "changed", before: { text: "a" }, after: { text: "b" } }],
      }),
    );
    expect([diff.from, diff.to]).toEqual(["a", "b"]);
  });
  it("US-18 AC4: an op kind web does not know still gives a sentence", () => {
    expect(diffOf(applied({ op_kinds: ["new_kind"] })).noun).toBe("phần");
  });
});

describe("run", () => {
  it("US-18 AC1: sends command_id, screen_session_id, subject_id and text; done refreshes the screen", async () => {
    const fetchFn = reply(200, applied());
    const live = setup();
    const outcome = await live.run(CMD, signal);
    expect(outcome.kind).toBe("done");
    const init = fetchFn.mock.calls[0]![1]!;
    expect(JSON.parse(init.body as string)).toEqual({
      command_id: CMD.id,
      screen_session_id: "x",
      subject_id: "s",
      text: CMD.text,
    });
    expect(live.changed).toHaveBeenCalledOnce();
  });

  // Red when: an unclear answer is guessed at, or the screen is refreshed for a command that did nothing.
  it("US-18 AC3: unclear gives the reason and changes nothing", async () => {
    reply(200, { status: "unclear", reason: "unknown_target" });
    const live = setup();
    expect(await live.run(CMD, signal)).toEqual({ kind: "unclear", reason: "unknown_target" });
    expect(live.changed).not.toHaveBeenCalled();
  });

  it("US-18 AC8: 429 quota_hard_cap turns the bar off; another 429 is an error", async () => {
    reply(429, { error: "quota_hard_cap" });
    expect((await setup().run(CMD, signal)).kind).toBe("pending-ai");
    reply(429, { error: "rate_limited" });
    expect(await setup().run(CMD, signal)).toEqual({ kind: "error", certain: true });
  });

  it("US-18 AC4: 409, a refused command and a parser that did not answer say nothing changed", async () => {
    for (const [status, error] of [
      [409, "command_id_reused"],
      [422, "rejected"],
      [503, "parse_unavailable"],
    ] as const) {
      reply(status, { error });
      expect(await setup().run(CMD, signal)).toEqual({ kind: "error", certain: true });
    }
  });

  it("US-18 AC4: unsupported is not allowed by command", async () => {
    reply(422, { error: "unsupported" });
    expect(await setup().run(CMD, signal)).toEqual({ kind: "not-allowed" });
  });

  it("US-18 AC4: a lost connection or a 503 from web is unsure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Promise.reject(new TypeError("lost"))),
    );
    expect(await setup().run(CMD, signal)).toEqual({ kind: "error", certain: false });
    reply(503, { error: "unavailable" });
    expect(await setup().run(CMD, signal)).toEqual({ kind: "error", certain: false });
  });

  it("US-18 AC1: signed out sends the learner to the sign-in page", async () => {
    reply(401, { error: "signed_out" });
    const live = setup();
    await live.run(CMD, signal);
    expect(live.signedOut).toHaveBeenCalledOnce();
  });
});

describe("undo", () => {
  it("US-18 AC4: undoes the newest applied command by its id, then the one before", async () => {
    const live = setup();
    reply(200, applied());
    await live.run(CMD, signal);
    await live.run({ ...CMD, id: "21111111-2222-4333-8444-555555555555" }, signal);
    const fetchFn = reply(200, { status: "undone" });
    expect(await live.undo(signal)).toEqual({ kind: "undone" });
    expect(await live.undo(signal)).toEqual({ kind: "undone" });
    expect(fetchFn.mock.calls.map((c) => c[0] as string)).toEqual([
      "/api/commands/21111111-2222-4333-8444-555555555555/undo",
      `/api/commands/${CMD.id}/undo`,
    ]);
    expect(live.changed).toHaveBeenCalledTimes(4);
  });

  it("US-18 AC4: a refused undo keeps the command and gives a short neutral reason", async () => {
    const live = setup();
    reply(200, applied());
    await live.run(CMD, signal);
    for (const code of ["not_latest", "changed_after", "other_session"]) {
      reply(409, { error: code });
      expect((await live.undo(signal)).kind).toBe("undo-failed");
    }
    const fetchFn = reply(200, { status: "undone" });
    expect(await live.undo(signal)).toEqual({ kind: "undone" });
    expect(fetchFn).toHaveBeenCalledOnce();
  });

  it("US-18 AC4: an unknown failure of undo is a throw (the bar says it is not sure)", async () => {
    const live = setup();
    reply(200, applied());
    await live.run(CMD, signal);
    reply(503, { error: "unavailable" });
    await expect(live.undo(signal)).rejects.toThrow();
  });
});
