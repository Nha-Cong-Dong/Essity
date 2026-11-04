import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { GuideArt } from "@/components/today-v2/guide-art";
import { STEPS } from "@/components/today-v2/learn-actions";

// UI-A (user 05/11): "Hướng dẫn học" is five steps with a small animation each, still under reduced motion.
describe("learn guide", () => {
  it("has the four owner steps in order, then where the cards go, with the button names of the real screen", () => {
    expect(STEPS).toHaveLength(5);
    const text = STEPS.map((s) => `${s.title} ${s.body}`).join(" ");
    expect(STEPS[0].title).toMatch(/Vào buổi học/);
    expect(STEPS[2].body).toContain("Bạn đã học gì");
    expect(STEPS[2].body).toContain("Ghi lại");
    expect(STEPS[3].title).toContain("Hoàn thành");
    expect(STEPS[4].body).toContain("Kho kiến thức");
    expect(text).not.toMatch(/Duyệt thẻ|thẻ nháp|nháp/i);
  });

  it("draws a decorative animation for every step", () => {
    for (let i = 0; i < STEPS.length; i++) {
      const html = renderToStaticMarkup(<GuideArt step={i} />);
      expect(html).toContain('aria-hidden="true"');
      expect(html).toMatch(/guide-/);
    }
  });

  it("runs the keyframes only when motion is allowed", () => {
    const css = readFileSync("app/globals.css", "utf8").replace(/\r\n/g, "\n");
    const block = css.slice(css.indexOf("/* \"Hướng dẫn học\""));
    const motion = block.slice(block.indexOf("@media (prefers-reduced-motion: no-preference) {"), block.indexOf("@keyframes guide-in"));
    for (const cls of [".guide-step", ".guide-press", ".guide-hop", ".guide-card"]) expect(motion).toContain(cls);
    expect(block.slice(0, block.indexOf("@media"))).not.toMatch(/animation:/);
  });
});
