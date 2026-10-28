// T4.6 (US-01 AC7): the browser's side of an upload, with web's routes and storage faked.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { checkFile, MAX_FILE_BYTES, sha256Hex, type UploadState, uploadPdf } from "@/lib/upload-client";
import { uploadMessage } from "@/lib/upload-copy";

const go = vi.fn();
vi.mock("@/lib/navigate", () => ({ go: (path: string) => go(path) }));

const SUBJECT = "9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b";
const DOC = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const SIGNED = { url: "https://storage.example/signed?sig=SECRET", headers: { "If-None-Match": "*" } };
const pdf = new File(["%PDF-1.7 hello"], "Slide MMT.pdf", { type: "application/pdf" });

const json = (body: unknown, status = 200) => Response.json(body, { status });

afterEach(() => vi.unstubAllGlobals());
beforeEach(() => go.mockClear());

function run(fetcher: (path: string, init: RequestInit) => Response, put = vi.fn(async () => 200)) {
  const calls: { path: string; body: unknown }[] = [];
  vi.stubGlobal("fetch", async (path: string, init: RequestInit) => {
    calls.push({ path, body: JSON.parse(String(init.body)) });
    return fetcher(path, init);
  });
  const states: UploadState[] = [];
  return { calls, states, put, done: uploadPdf(SUBJECT, pdf, (s) => states.push(s), put) };
}

describe("checkFile (US-01 AC7)", () => {
  // Red when: a non-PDF, an empty file or one over 100 MiB reaches the network.
  it("refuses what core-api would refuse, before sending", () => {
    expect(checkFile({ name: "a.pdf", size: 10 })).toBeNull();
    expect(checkFile({ name: "A.PDF", size: MAX_FILE_BYTES })).toBeNull();
    expect(checkFile({ name: "a.png", size: 10 })).toBe("not_pdf");
    expect(checkFile({ name: "a.pdf.exe", size: 10 })).toBe("not_pdf");
    expect(checkFile({ name: "a.pdf", size: 0 })).toBe("empty");
    expect(checkFile({ name: "a.pdf", size: MAX_FILE_BYTES + 1 })).toBe("too_big");
  });
});

describe("sha256Hex", () => {
  it("is the lowercase hex SHA-256 core-api asks for", async () => {
    expect(await sha256Hex(new Blob(["abc"]))).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    );
  });
});

describe("uploadPdf", () => {
  // Red when: the PUT lacks the signed headers, the file's facts are wrong, or confirm is skipped.
  it("asks, sends with the signed headers, confirms, and ends done", async () => {
    const { calls, states, put, done } = run((path) =>
      path.endsWith("/documents")
        ? json({ document: { id: DOC }, duplicate: false, upload: SIGNED }, 201)
        : json({ id: DOC, status: "uploaded" }),
    );
    await done;
    expect(calls[0]).toEqual({
      path: `/api/subjects/${SUBJECT}/documents`,
      body: { filename: "Slide MMT.pdf", size_bytes: pdf.size, sha256: await sha256Hex(pdf) },
    });
    expect(put).toHaveBeenCalledWith(SIGNED, pdf, expect.any(Function));
    expect(calls[1].path).toBe(`/api/documents/${DOC}/confirm`);
    expect(states.map((s) => s.kind)).toEqual(["hashing", "uploading", "checking", "done"]);
  });

  // Red when: a file already stored is sent again.
  it("a duplicate has no URL: no PUT, only confirm", async () => {
    const { put, calls, states, done } = run((path) =>
      path.endsWith("/documents")
        ? json({ document: { id: DOC }, duplicate: true, upload: null })
        : json({ id: DOC }),
    );
    await done;
    expect(put).not.toHaveBeenCalled();
    expect(calls).toHaveLength(2);
    expect(states.at(-1)).toEqual({ kind: "done" });
  });

  // Red when: a 412 (already there, If-None-Match) is shown as a failure.
  it("a 412 from storage still confirms", async () => {
    const { states, done } = run(
      (path) => (path.endsWith("/documents") ? json({ document: { id: DOC }, upload: SIGNED }, 201) : json({})),
      vi.fn(async () => 412),
    );
    await done;
    expect(states.at(-1)).toEqual({ kind: "done" });
  });

  it.each([
    [403, "upload_expired"],
    [500, "upload_failed"],
  ])("a %i from storage fails as %s and does not confirm", async (status, code) => {
    const { calls, states, done } = run(
      () => json({ document: { id: DOC }, upload: SIGNED }, 201),
      vi.fn(async () => status),
    );
    await done;
    expect(states.at(-1)).toEqual({ kind: "failed", code });
    expect(calls).toHaveLength(1);
  });

  it("a network failure during the PUT fails as offline", async () => {
    const { states, done } = run(
      () => json({ document: { id: DOC }, upload: SIGNED }, 201),
      vi.fn(async () => {
        throw new Error("network");
      }),
    );
    await done;
    expect(states.at(-1)).toEqual({ kind: "failed", code: "offline" });
  });

  it.each([
    [409, "storage_quota_exceeded"],
    [429, "rate_limited"],
    [422, "unsupported_file_type"],
  ])("web's %i %s ends failed with that code, no PUT", async (status, code) => {
    const { put, states, done } = run(() => json({ error: code }, status));
    await done;
    expect(states.at(-1)).toEqual({ kind: "failed", code });
    expect(put).not.toHaveBeenCalled();
  });

  it("confirm refused as content_mismatch ends failed", async () => {
    const { states, done } = run((path) =>
      path.endsWith("/documents")
        ? json({ document: { id: DOC }, upload: SIGNED }, 201)
        : json({ error: "content_mismatch" }, 422),
    );
    await done;
    expect(states.at(-1)).toEqual({ kind: "failed", code: "content_mismatch" });
  });

  it("signed out goes to /login", async () => {
    const { done } = run(() => json({ error: "signed_out" }, 401));
    await done;
    expect(go).toHaveBeenCalledWith("/login");
  });

  // Red when: the signed URL appears in a message the page shows.
  it("no state or message carries the signed URL", async () => {
    const { states, done } = run(
      () => json({ document: { id: DOC }, upload: SIGNED }, 201),
      vi.fn(async () => 403),
    );
    await done;
    expect(JSON.stringify(states)).not.toContain("SECRET");
    expect(uploadMessage("upload_expired")).not.toContain("SECRET");
  });
});
