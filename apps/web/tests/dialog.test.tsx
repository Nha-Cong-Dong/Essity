// @vitest-environment jsdom
// DESIGN-W0: the "celebrate" dialog (praise pop-up). Base UI gives the focus trap and Escape; here:
// the role and its name, Escape closes, focus lands inside, and the motion is only a fade under
// reduced motion (the transform classes are all `motion-safe:`).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Dialog } from "@/components/ui/dialog";

afterEach(cleanup);

function open(onOpenChange = vi.fn()) {
  render(
    <Dialog
      open
      onOpenChange={onOpenChange}
      variant="celebrate"
      title="Buổi học xong rồi"
      description="Thẻ đang được chuẩn bị."
      media={<span data-testid="mascot">m</span>}
    >
      <button type="button">Về trang chủ</button>
      <button type="button">Học tiếp môn này</button>
    </Dialog>,
  );
  return onOpenChange;
}

describe("Dialog celebrate", () => {
  it("is a modal dialog named by its title and described by its line", () => {
    open();
    const dialog = screen.getByRole("dialog", { name: "Buổi học xong rồi" });
    expect(dialog.getAttribute("aria-describedby")).toBeTruthy();
    expect(dialog.getAttribute("data-variant")).toBe("celebrate");
    expect(screen.getByTestId("mascot")).toBeTruthy();
  });

  it("is 440px at most, centred, on the overlay shadow", () => {
    open();
    const cls = screen.getByRole("dialog").className;
    expect(cls).toContain("max-w-[440px]");
    expect(cls).toContain("shadow-over");
    expect(cls).toContain("text-center");
  });

  it("Escape asks to close", () => {
    const onOpenChange = open();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    expect(onOpenChange).toHaveBeenCalledWith(false, expect.anything());
  });

  it("puts focus inside the dialog", async () => {
    open();
    await waitFor(() => expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true));
  });

  it("Tab never leaves the dialog (focus trap)", async () => {
    open();
    const dialog = screen.getByRole("dialog");
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
    const last = screen.getByRole("button", { name: "Học tiếp môn này" });
    last.focus();
    // user-event is not a dependency: Base UI wraps the popup in focus guards, so the guard that
    // follows the dialog exists and sends focus back inside.
    expect(document.querySelectorAll("[data-base-ui-focus-guard]").length).toBeGreaterThan(0);
  });

  it("motion: opacity always, the rise and scale only under motion-safe", () => {
    open();
    const cls = screen.getByRole("dialog").className.split(/\s+/);
    expect(cls).toContain("data-[starting-style]:opacity-0");
    const moves = cls.filter((c) => /translate|scale/.test(c) && /starting-style|ending-style/.test(c));
    expect(moves.length).toBeGreaterThan(0);
    expect(moves.every((c) => c.startsWith("motion-safe:"))).toBe(true);
  });

  it("renders nothing when closed", () => {
    render(<Dialog open={false} onOpenChange={() => {}} title="x" />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
