import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { EmptyState } from "@/components/empty-state";

describe("EmptyState (UI-1b)", () => {
  const markup = renderToStaticMarkup(
    h(EmptyState, { title: "Chưa có môn nào.", hint: "Tạo môn đầu tiên.", action: h("a", { href: "/x" }, "Tạo môn") }),
  );

  it("is a lead sentence, a soft sentence under it and one action", () => {
    expect(markup).toMatch(/<p class="m-0 text-lead">Chưa có môn nào\.<\/p>/);
    expect(markup).toMatch(/<p class="m-0 text-body text-ink-soft">Tạo môn đầu tiên\.<\/p>/);
    expect(markup.match(/<a /g)).toHaveLength(1);
  });

  it("drops the hint and the action when there are none", () => {
    const bare = renderToStaticMarkup(h(EmptyState, { title: "Trống." }));
    expect(bare.match(/<p /g)).toHaveLength(1);
    expect(bare).not.toMatch(/<a |<button/);
  });
});
