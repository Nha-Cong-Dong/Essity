// @vitest-environment jsdom
// C5-V4-SWEEP: guards for the loose ends of the v4 pass. No behaviour changed.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EmptyState } from "@/components/empty-state";
import { ForgotPassword } from "@/components/auth/forgot-password";
import { SyllabusScreen } from "@/components/syllabus/syllabus-screen";
import { UploadScreen } from "@/components/syllabus/upload-files";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const src = (rel: string) => readFileSync(join(__dirname, "..", rel), "utf8");

describe("R74: forgot-password 'sent' notice", () => {
  // Red when: the sent state loses role="status" (a screen reader would not hear it).
  it("announces the sent state through role=status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } })),
    );
    const { container } = render(<ForgotPassword />);
    fireEvent.change(container.querySelector("input[name=email]")!, { target: { value: "a@b.vn" } });
    fireEvent.submit(container.querySelector("form")!);
    const status = await waitFor(() => screen.getByRole("status"));
    expect(status.textContent).toMatch(/a.*@/);
    expect(status.querySelector("a[href='/login']")).not.toBeNull();
  });
});

describe("C2/C3: no raw rose scale and no pink block on the pink page", () => {
  // Red when: the upload tray goes back to bg-rose-*, or the exclude editor to rose-100/700.
  it("upload tray and exclude editor use tokens", () => {
    expect(src("components/syllabus/upload-files.tsx")).not.toMatch(/rose-\d/);
    expect(src("components/syllabus/exclude-editor.tsx")).not.toMatch(/rose-\d/);
  });

  // Red when: FocusShell stops turning --sunken into the sheet colour (sunken is invisible on --bg).
  it("FocusShell redefines --sunken as the sheet", () => {
    expect(src("components/shells.tsx")).toMatch(/\[--sunken:var\(--sheet\)\]/);
  });

  it("empty upload tray is a sheet", () => {
    render(<UploadScreen state="upload-empty" />);
    const tray = screen.getByText(/Chưa có tài liệu/).parentElement!;
    expect(tray.className).toMatch(/bg-sheet/);
  });
});

describe("Đề cương on a phone: one name, one accent", () => {
  // Red when: the tile's subject heading shows again at 390 (it repeats the back link).
  it("the tile heading is sr-only below 640px and the tile is flat there", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    const tile = container.querySelector("[data-nx]")!;
    expect(tile.className).toMatch(/max-\[640px\]:bg-transparent/);
    expect(tile.className).toMatch(/max-\[640px\]:border-0/);
    expect(tile.querySelector("h2")!.className).toMatch(/max-\[640px\]:sr-only/);
  });

  // Red when: the suggested row takes the coral accent again (the pink button is the one accent).
  it("the suggested row is marked without the cam accent", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    const next = container.querySelector("[data-row].font-semibold[class*='inset-ring-ink']");
    expect(next).not.toBeNull();
    expect(src("components/syllabus/syllabus-tree.tsx")).not.toMatch(/NX_CAM|text-cam|inset-ring-cam/);
  });
});

describe("Đề cương load failure keeps the aside below the alert", () => {
  // Red when: the error branch of the page loses role=alert or the retry link, or the aside goes.
  it("page.tsx: error block has role=alert + retry, aside is labelled", () => {
    const page = src("app/subjects/[id]/syllabus/page.tsx");
    expect(page).toMatch(/<Block role="alert"/);
    expect(page).toMatch(/Thử lại/);
    expect(page).toMatch(/as="aside"[\s\S]*aria-label="Chỉnh đề cương bằng lời"/);
    expect(page.indexOf("<Syllabus params")).toBeLessThan(page.indexOf('as="aside"'));
  });
});

describe("M1/M2: mascot art and roles", () => {
  // Red when: the pink mouth stroke (#ec5493) or a beard comes back into the art.
  it("art has no #ec5493 stroke", () => {
    expect(src("components/mascot-art.tsx").toLowerCase()).not.toContain("ec5493");
  });

  // Red when: the praise/done screens go back to the cloud, or the sign-in goes back to the cloud.
  it("praise and done use the sun; assistant screens keep the cloud", () => {
    expect(src("components/review/summary.tsx")).toMatch(/<Mascot kind="sun" pose="khen"/);
    expect(src("components/review/review-screen.tsx")).toMatch(/mascot="khen"\s+mascotKind="sun"/);
    expect(src("components/auth/auth-layout.tsx")).not.toMatch(/kind="cloud"/);
    expect(src("components/landing/landing.tsx")).toMatch(/kind="cloud"/);
  });

  it("EmptyState passes the kind to the mascot", () => {
    const { container } = render(<EmptyState title="x" mascot="khen" mascotKind="sun" />);
    expect(container.querySelector("[data-mascot-kind=sun]")).not.toBeNull();
    const { container: c2 } = render(<EmptyState title="x" mascot="rong" />);
    expect(c2.querySelector("[data-mascot-kind=cloud]")).not.toBeNull();
  });
});

describe("C5 M2: mascot by role (structure)", () => {
  it("auth is the sun (chao), landing is the cloud (chao)", () => {
    expect(src("components/auth/auth-layout.tsx")).toMatch(/kind="sun" pose="chao"/);
    expect(src("components/landing/landing.tsx")).toMatch(/kind="cloud" pose="chao"/);
  });
  it("screens with hint/wait/empty poses leave the kind default (cloud)", () => {
    for (const f of ["components/vault/vault-view.tsx", "components/practice/practice-live.tsx", "components/stats/stats-screen.tsx"]) {
      expect(src(f)).not.toMatch(/kind="sun"/);
    }
  });
});
