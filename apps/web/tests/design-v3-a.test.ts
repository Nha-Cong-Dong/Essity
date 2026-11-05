// DESIGN-A (direction §C/§F3): Hôm nay layout. Red when: the h1 keeps its highlighter, the review is not the plum
// field at column 5, "Học gì tiếp theo?" loses column 7, a zero day prints a "0", or a colour is hard-coded.
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { WeekStrip, weekFromCells } from "@/components/today-v2/week-strip";
import { TodayV2Screen } from "@/components/today-v2/today-v2-screen";
import { TODAY_STATES } from "@/lib/fixtures/today-v2";

const draw = (state: string, week = false) =>
  renderToStaticMarkup(
    createElement(TodayV2Screen, {
      today: TODAY_STATES[state],
      week: week ? weekFromCells([], TODAY_STATES[state].learning_day) : undefined,
    }),
  );

describe("DESIGN-A Hôm nay", () => {
  it("the h1 has no highlighter", () => {
    const markup = draw("review");
    expect(markup).not.toContain("hl-word");
    expect(markup).toMatch(/<h1[^>]*>Hôm nay<\/h1>/);
  });

  it("row 1: Học gì tiếp theo? is column 7 and comes first; the review is the plum field at column 5", () => {
    const markup = draw("review");
    const learn = markup.indexOf('aria-labelledby="today-learn"');
    const review = markup.indexOf('aria-labelledby="today-review"');
    expect(learn).toBeGreaterThan(-1);
    expect(learn).toBeLessThan(review);
    expect(markup.slice(markup.lastIndexOf("<section", learn), learn)).toContain("col-span-7");
    const field = markup.slice(markup.lastIndexOf("<section", review), review);
    expect(field).toContain("col-span-5");
    expect(field).toContain("bg-plum");
    expect(field).toContain('data-tier="field"');
  });

  it("with cards due: the number, one Bắt đầu ôn button, one doodle", () => {
    const markup = draw("review");
    expect(markup).toContain("Bắt đầu ôn");
    expect(markup.match(/data-motif="doodle"/g)).toHaveLength(1);
  });

  it("with no cards due: Xong phần ôn hôm nay and the yellow sticker, still the field", () => {
    const markup = draw("learn");
    expect(markup).toContain("Xong phần ôn hôm nay");
    expect(markup).toContain('data-motif="sticker"');
    expect(markup).toContain('data-tier="field"');
  });

  it("row 2: Luyện tập is column 7, Tuần này column 5", () => {
    const markup = draw("learn", true);
    const at = (id: string) => {
      const i = markup.indexOf(`aria-labelledby="${id}"`);
      return markup.slice(markup.lastIndexOf("<section", i), markup.indexOf(">", i));
    };
    expect(at("today-practice")).toContain("col-span-7");
    expect(at("today-week")).toContain("col-span-5");
  });

  it("Tuần này: today is the cam-fill bar with a dot; a day with 0 prints no number", () => {
    const week = weekFromCells([{ day: "2026-11-03", cardsSaved: 2, questionsAnswered: 1 }], "2026-11-04");
    const html = renderToStaticMarkup(createElement(WeekStrip, { cells: week, today: "2026-11-04" }));
    expect(html).toContain('data-bar="today"');
    expect(html).toContain("cam-fill");
    expect(html).not.toMatch(/<b[^>]*>0<\/b>/);
    expect(html.match(/<b[^>]*>\d+<\/b>/g)).toEqual([expect.stringContaining(">3<")]);
  });

  it("no colour is hard-coded in components/today-v2 outside a var() fallback", () => {
    const dir = path.join(__dirname, "..", "components", "today-v2");
    for (const file of readdirSync(dir)) {
      const src = readFileSync(path.join(dir, file), "utf8");
      const bare = src.replace(/var\([^)]*\)/g, "").replace(/color-mix\([^)]*\)/g, "");
      expect(bare.match(/#[0-9a-fA-F]{3,8}\b/g) ?? [], file).toEqual([]);
    }
  });
});
