// T7.12c (US-02 AC1, AC13): a file of a study session's submission, from the browser to storage.
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  checkSubmissionFile,
  FILE_MAX_BYTES,
  type FileState,
  rowStateOf,
  submissionMime,
  uploadSubmissionFile,
} from "@/lib/session-study/files";

vi.mock("@/lib/navigate", () => ({ go: () => undefined }));

const SESSION = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const SIGNED = { url: "https://storage.example/signed?sig=SECRET", headers: { "If-None-Match": "*" } };
// SHA-256 of "abc", written here, not computed by the code under test.
const ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
const PNG = () => new File(["abc"], "x.png", { type: "image/png" });
afterEach(() => vi.unstubAllGlobals());

function run(file: File, answer: () => Response, put = vi.fn(async () => 200)) {
  const calls: { path: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", async (path: string, init: RequestInit) => {
    calls.push({ path, body: JSON.parse(String(init.body)) });
    return answer();
  });
  const states: FileState[] = [];
  return { calls, states, put, done: uploadSubmissionFile(SESSION, file, (s) => states.push(s), put) };
}

describe("check and type", () => {
  // Red when: Word or PowerPoint is refused, or a type core-api refuses is sent.
  it("takes the types core-api takes and refuses the rest, empty and big files", () => {
    expect(submissionMime({ name: "a.DOCX", type: "" })).toContain("wordprocessingml");
    expect(submissionMime({ name: "a.pptx", type: "" })).toContain("presentationml");
    expect(checkSubmissionFile({ name: "a.exe", type: "", size: 5 })).toBe("unsupported");
    expect(checkSubmissionFile({ name: "a.gif", type: "image/gif", size: 5 })).toBe("unsupported");
    expect(checkSubmissionFile({ name: "a.png", type: "image/png", size: 0 })).toBe("empty");
    expect(checkSubmissionFile({ name: "a.png", type: "image/png", size: FILE_MAX_BYTES + 1 })).toBe("too_big");
    expect(checkSubmissionFile({ name: "a.png", type: "image/png", size: FILE_MAX_BYTES })).toBeNull();
  });

  it("maps a failure to the row's words", () => {
    expect(rowStateOf("unsupported")).toBe("bad-type");
    expect(rowStateOf("too_big")).toBe("too-big");
    expect(rowStateOf("file_too_large")).toBe("too-big");
    expect(rowStateOf("offline")).toBe("net-error");
    expect(rowStateOf("upload_expired")).toBe("net-error");
  });
});

describe("uploadSubmissionFile", () => {
  // Red when: the hash, type or size handed back differ from what was asked, or the signed URL leaks.
  it("asks for a URL, sends the file, and hands back its hash, type and size", async () => {
    const { calls, states, put, done } = run(PNG(), () => Response.json(SIGNED, { status: 201 }));
    await done;
    expect(calls[0].path).toBe(`/api/sessions/${SESSION}/notes/upload-url`);
    expect(calls[0].body).toEqual({ sha256: ABC, mime: "image/png", size_bytes: 3 });
    expect(put).toHaveBeenCalledTimes(1);
    expect(states.at(-1)).toEqual({ kind: "ready", ref: { sha256: ABC, mime: "image/png", size_bytes: 3 } });
    expect(JSON.stringify(states)).not.toContain("SECRET");
  });

  it("a wrong type fails before anything is sent", async () => {
    const { calls, states, done } = run(new File(["x"], "x.exe"), () => Response.json(SIGNED));
    await done;
    expect(calls).toHaveLength(0);
    expect(states.at(-1)).toEqual({ kind: "failed", code: "unsupported" });
  });

  it("a refusal, an expired URL and a dropped network are failures with a code", async () => {
    const refused = run(PNG(), () => Response.json({ error: "file_too_large" }, { status: 422 }));
    await refused.done;
    expect(refused.states.at(-1)).toEqual({ kind: "failed", code: "file_too_large" });
    const expired = run(PNG(), () => Response.json(SIGNED, { status: 201 }), vi.fn(async () => 403));
    await expired.done;
    expect(expired.states.at(-1)).toEqual({ kind: "failed", code: "upload_expired" });
    const dropped = run(PNG(), () => Response.json(SIGNED, { status: 201 }), vi.fn(() => Promise.reject(new Error("x"))));
    await dropped.done;
    expect(dropped.states.at(-1)).toEqual({ kind: "failed", code: "offline" });
  });

  it("412 means the file is already there: ready", async () => {
    const r = run(PNG(), () => Response.json(SIGNED, { status: 201 }), vi.fn(async () => 412));
    await r.done;
    expect(r.states.at(-1)?.kind).toBe("ready");
  });
});
