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
