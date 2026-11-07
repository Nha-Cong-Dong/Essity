// @vitest-environment jsdom
// SCREENS-V4-B (user 08/11): every Kho card has the mockup's fixed size; long content scrolls inside it.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { CardList } from "@/components/vault/card-list";

afterEach(cleanup);

const card = (id: string, content: string) => ({ id, title: `Thẻ ${id}`, content }) as never;

// Red when: a card grows with its content (min-height) instead of keeping 360px with an inner scroll.
it("a card is a fixed 360px tall and its body is a focusable, labelled scroll region", () => {
  const long = Array.from({ length: 60 }, (_, i) => `Dòng ${i}`).join("\n\n");
  const { container } = render(<CardList cards={[card("a", long), card("b", "ngắn")]} />);
  const articles = container.querySelectorAll('[data-slot="vault-card"]');
  expect(articles.length).toBe(2);
  for (const a of articles) {
    expect(a.className).toContain("h-[360px]");
    expect(a.className).not.toContain("min-h-");
  }
  const region = screen.getByRole("region", { name: "Nội dung thẻ: Thẻ a" });
  expect(region.getAttribute("tabindex")).toBe("0");
  expect(region.className).toContain("overflow-y-auto");
  // The title and the buttons are outside the scrolling body.
  expect(region.contains(screen.getAllByText("Sửa thẻ")[0])).toBe(false);
  expect(region.contains(screen.getByText("Thẻ a"))).toBe(false);
});
