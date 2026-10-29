// T4.13b (US-02 AC13): the browser's side of a note upload, with web's routes and storage faked.
import { afterEach, describe, expect, it, vi } from "vitest";

import { checkNote, NOTE_MAX_BYTES, type NoteState, noteMime, uploadNote } from "@/lib/note-upload";

vi.mock("@/lib/navigate", () => ({ go: () => undefined }));

const SESSION = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const SIGNED = { url: "https://storage.example/signed?sig=SECRET", headers: { "If-None-Match": "*" } };
const photo = new File(["abc"], "trang 5.JPG", { type: "image/jpeg" });
// SHA-256 of "abc", written here, not computed by the code under test.
const ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

afterEach(() => vi.unstubAllGlobals());

function run(fetcher: (path: string) => Response, put = vi.fn(async () => 200), file: File = photo) {
  const calls: { path: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", async (path: string, init: RequestInit) => {
    calls.push({ path, body: JSON.parse(String(init.body)) });
    return fetcher(path);
  });
  const states: NoteState[] = [];
  return { calls, states, put, done: uploadNote(SESSION, file, (s) => states.push(s), put) };
}

describe("checkNote", () => {
  // Red when: a type core-api would refuse, an empty file or one over 20 MiB reaches the network.
  it("refuses what core-api would refuse, before sending", () => {
    expect(checkNote({ name: "a.jpg", type: "image/jpeg", size: 10 })).toBeNull();
    expect(checkNote({ name: "a.md", type: "", size: NOTE_MAX_BYTES })).toBeNull();
    expect(checkNote({ name: "a.gif", type: "image/gif", size: 10 })).toBe("unsupported");
    expect(checkNote({ name: "a.html", type: "text/html", size: 10 })).toBe("unsupported");
    expect(checkNote({ name: "a.png", type: "image/png", size: 0 })).toBe("empty");
    expect(checkNote({ name: "a.png", type: "image/png", size: NOTE_MAX_BYTES + 1 })).toBe("too_big");
  });

  it("takes the type from the browser, or from the extension when it has none", () => {
    expect(noteMime({ name: "x.bin", type: "image/png" })).toBe("image/png");
    expect(noteMime({ name: "ghi chú.TXT", type: "" })).toBe("text/plain");
    expect(noteMime({ name: "x.jpeg", type: "" })).toBe("image/jpeg");
    expect(noteMime({ name: "x.exe", type: "" })).toBeNull();
  });
});

describe("uploadNote", () => {
  // Red when: the hash, type or size asked for is not the file's, or the file is not sent with
  // the headers core-api signed.
  it("asks for a URL for the file's hash, type and size, sends it, and hands back the note", async () => {
    const { calls, states, put, done } = run(() => Response.json(SIGNED, { status: 201 }));
    await done;
    const note = { sha256: ABC, mime: "image/jpeg", size_bytes: 3 };
    expect(calls).toEqual([{ path: `/api/sessions/${SESSION}/notes/upload-url`, body: note }]);
    expect(put).toHaveBeenCalledWith(SIGNED, photo, expect.any(Function));
    expect(states.map((s) => s.kind)).toEqual(["hashing", "uploading", "ready"]);
    expect(states.at(-1)).toEqual({ kind: "ready", note });
  });

  // Red when: a store that already has the file (412) fails the note.
  it("treats 412 as stored", async () => {
    const { states, done } = run(
      () => Response.json(SIGNED),
      vi.fn(async () => 412),
    );
    await done;
    expect(states.at(-1)?.kind).toBe("ready");
  });

  it.each([
    [403, "upload_expired"],
    [500, "upload_failed"],
  ])("a %i from storage is %s", async (status, code) => {
    const { states, done } = run(
      () => Response.json(SIGNED),
      vi.fn(async () => status),
    );
    await done;
    expect(states.at(-1)).toEqual({ kind: "failed", code });
  });

  it("a network error while sending is offline", async () => {
    const { states, done } = run(
      () => Response.json(SIGNED),
      vi.fn(async () => {
        throw new Error("network");
      }),
    );
    await done;
    expect(states.at(-1)).toEqual({ kind: "failed", code: "offline" });
  });

  // Red when: a refusal of core-api is lost, or storage is called after one.
  it.each(["storage_quota_exceeded", "too_many_notes", "session_confirmed"])(
    "core-api's %s stops the note before storage",
    async (error) => {
      const { states, put, done } = run(() => Response.json({ error }, { status: 409 }));
      await done;
      expect(states.at(-1)).toEqual({ kind: "failed", code: error });
      expect(put).not.toHaveBeenCalled();
    },
  );

  it("never puts the signed URL in a state", async () => {
    const { states, done } = run(() => Response.json(SIGNED, { status: 201 }));
    await done;
    expect(JSON.stringify(states)).not.toContain("SECRET");
  });

  it("a type not allowed never reaches the network", async () => {
    const { calls, states, done } = run(
      () => Response.json(SIGNED),
      vi.fn(async () => 200),
      new File(["x"], "a.gif", { type: "image/gif" }),
    );
    await done;
    expect(calls).toHaveLength(0);
    expect(states).toEqual([{ kind: "failed", code: "unsupported" }]);
  });
});
