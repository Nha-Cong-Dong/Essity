// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FileDrop } from "@/components/session-study/session-file-drop";

// C4D: mockup session.html. Files are chips (paperclip), not a dashed drop box, in the pieces composer.
describe("C4D attachment chip", () => {
  const rows = [{ id: "1", name: "Bai-tap-chuong-1.pdf", kind: "pdf" as const, state: "done" as const }];
  const noop = () => {};
  it("chips mode shows a chip and no dashed picker", () => {
    render(<FileDrop chips rows={rows} onAdd={noop} onRemove={noop} onRetry={noop} />);
    expect(screen.getByTestId("attach-chips").textContent).toContain("Bai-tap-chuong-1.pdf");
    expect(screen.queryByText("Chọn file")).toBeNull();
  });
  it("default mode keeps the drop box", () => {
    render(<FileDrop rows={rows} onAdd={noop} onRemove={noop} onRetry={noop} />);
    expect(screen.getByText("Chọn file")).toBeTruthy();
  });
});

// Dropping a file anywhere on the composer attaches it, as the dashed box did before chips mode.
import { fireEvent } from "@testing-library/react";
import { type SessionInitial, SessionScreen } from "@/components/session-study/session-screen";
import type { SessionApi } from "@/lib/session-study/api";
import { initialRound } from "@/lib/session-study/round";
import { vi } from "vitest";

describe("C4D drop onto the composer", () => {
  it("a dropped file becomes a chip", async () => {
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
    Element.prototype.scrollIntoView = vi.fn();
    const api = {
      sessionId: "s1",
      pieces: vi.fn(() => Promise.resolve({ ok: true, data: { pieces: [], submitted: false } })),
      addPiece: vi.fn(), removePiece: vi.fn(), complete: vi.fn(), submit: vi.fn(), upload: vi.fn(), result: vi.fn(),
    };
    const initial: SessionInitial = { round: { ...initialRound }, text: "", mentions: [], files: [] };
    const FREE = { kind: "free", text: "x" } as const;
    render(<SessionScreen api={api as unknown as SessionApi} subject="M" subjectId="S" stopHref="/today" docs={[]} suggestion={FREE} nextSuggestion={FREE} initial={initial} />);
    const composer = (await screen.findByText("Bạn đã học gì?")).closest("section") as HTMLElement;
    const file = new File(["x"], "bai.pdf", { type: "application/pdf" });
    fireEvent.drop(composer, { dataTransfer: { files: [file] } });
    expect(await screen.findByText("bai.pdf")).toBeTruthy();
  });
});
