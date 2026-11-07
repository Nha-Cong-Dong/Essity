// @vitest-environment jsdom
// CARD-MD: a card's Markdown shows maths and stays safe.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { Markdown } from "@/components/markdown/markdown";

afterEach(cleanup);

// Flaky fix (A2): the Markdown chunk (react-markdown + KaTeX) loads lazily; on a busy machine the
// first test paid for that import inside its own timeout. Load it once, up front, with a long limit.
beforeAll(async () => {
  await import("@/components/markdown/markdown-inner");
}, 60_000);

async function drawn(text: string) {
  const { container } = render(<Markdown text={text} />);
  await waitFor(() => expect(container.querySelector("p")).not.toBeNull(), { timeout: 8000 });
  return container;
}

describe("Markdown card", () => {
  // Red when: a formula stays as "$n_1 n_2$" text instead of being typeset.
  it("typesets inline and block maths", async () => {
    const c = await drawn(String.raw`Quy tắc nhân $n_1 n_2 \cdots n_k$ và

$$
P(A\mid B)=\frac{P(AB)}{P(B)}
$$`);
    expect(c.querySelectorAll(".katex").length).toBe(2);
    expect(c.querySelector(".katex-display")).not.toBeNull();
    expect(c.textContent).not.toContain("$");
  });

  // Red when: Markdown marks show as raw characters.
  it("renders bold, lists and code", async () => {
    const c = await drawn("**đậm** và `mã`\n\n- một\n- hai");
    expect(c.querySelector("strong")?.textContent).toBe("đậm");
    expect(c.querySelector("code")?.textContent).toBe("mã");
    expect(c.querySelectorAll("li")).toHaveLength(2);
  });

  // Red when: an old plain-text card changes its words or loses its line breaks.
  it("keeps a plain-text card as it was", async () => {
    const { container } = render(<Markdown text={"Dòng một\nDòng hai"} />);
    await waitFor(() => expect(container.querySelector("p")).not.toBeNull(), { timeout: 8000 });
    expect(container.textContent).toBe("Dòng một\nDòng hai");
    expect((container.firstElementChild as HTMLElement).className).toContain("whitespace-pre-line");
  });

  // Red when: raw HTML in a card reaches the page (XSS).
  it("never lets raw HTML, scripts, handlers or images through", async () => {
    const c = await drawn(
      'ok <script>window.__x=1</script><img src=x onerror="window.__x=2"><b onclick="window.__x=3">b</b>\n\n<iframe src="https://e.com"></iframe>\n\n[x](javascript:alert(1)) ![i](https://e.com/a.png)',
    );
    expect(c.querySelector("script, iframe, img")).toBeNull();
    for (const el of c.querySelectorAll("*")) expect([...el.attributes].filter((a) => /^on/i.test(a.name))).toEqual([]);
    expect((window as unknown as { __x?: number }).__x).toBeUndefined();
    for (const a of c.querySelectorAll("a")) expect(a.getAttribute("href") ?? "").not.toMatch(/^javascript:/i);
  });

  // Red when: a link opens with access to the opener.
  it("links open safely", async () => {
    const c = await drawn("[trang](https://example.com)");
    const a = c.querySelector("a");
    expect(a?.getAttribute("rel")).toContain("noopener");
    expect(a?.getAttribute("target")).toBe("_blank");
  });

  // Red when: a broken formula or a KaTeX trust trick throws or navigates.
  it("a bad formula does not throw and \href is not followed", async () => {
    const c = await drawn(String.raw`$\frac{1$ và $\href{javascript:alert(1)}{x}$`);
    expect(c.querySelector("a[href^='javascript']")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
