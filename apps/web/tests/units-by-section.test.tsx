// @vitest-environment jsdom
// T7.12d (US-02b AC14): the subject's cards by outline section.
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UnitsBySection } from "@/components/session-study/units-by-section";
import { loadUnitsBySection } from "@/lib/session-study/by-section";

afterEach(cleanup);

const GROUPS = {
  groups: [
    { section_id: "s1", section_title: "Chương 1", units: [{ id: "a", title: "Thẻ A", content: "Ý A", kind: "concept", status: "canonical" }] },
    { section_id: null, section_title: null, units: [{ id: "b", title: "Thẻ B", content: "Ý B", kind: "concept", status: "draft" }] },
  ],
};
const reply = (status: number, body: unknown) => vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;

describe("AC14 units by section", () => {
  it("AC14 shows a group per section and the cards in none under their own heading", async () => {
    render(<UnitsBySection subjectId="x" fetchFn={reply(200, GROUPS)} />);
    await waitFor(() => expect(screen.getByRole("heading", { name: /Thẻ theo mục/ })).toBeTruthy());
    expect(screen.getByRole("heading", { name: /Chương 1/ })).toBeTruthy();
    const loose = screen.getByRole("heading", { name: /Chưa gắn mục/ }).parentElement!;
    expect(within(loose).getByText(/Thẻ B/)).toBeTruthy();
    expect(within(loose).getByText(/nháp/)).toBeTruthy();
  });

  it("AC14 shows nothing for no cards and a neutral line when the read fails", async () => {
    const { container } = render(<UnitsBySection subjectId="x" fetchFn={reply(200, { groups: [] })} />);
    await waitFor(() => expect(container.textContent).toBe(""));
    cleanup();
    render(<UnitsBySection subjectId="x" fetchFn={reply(500, {})} />);
    await waitFor(() => expect(screen.getByText(/Chưa tải được/)).toBeTruthy());
  });

  it("AC14 loader returns null on a dropped network", async () => {
    const down = vi.fn(async () => {
      throw new Error("x");
    }) as unknown as typeof fetch;
    expect(await loadUnitsBySection("x", down)).toBeNull();
  });
});
