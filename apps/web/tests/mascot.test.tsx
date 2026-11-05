import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { EmptyState } from "@/components/empty-state";
import { Mascot, type MascotPose } from "@/components/mascot";

const POSES: MascotPose[] = ["chao", "khen", "nghi", "cho", "rong", "glyph", "vui", "chucmung", "chuanbi"];

describe("Mascot (MASCOT-V2, the magician cloud)", () => {
  // Red when: a pose is missing, or the mascot is announced to a screen reader.
  it.each(POSES)("%s is decoration: aria-hidden and a data-mascot mark", (pose) => {
    const markup = renderToStaticMarkup(<Mascot pose={pose} />);
    expect(markup).toContain('aria-hidden="true"');
    expect(markup).toContain(`data-mascot="${pose}"`);
  });

  // Red when: the first phase's names stop resolving to the v4 art (every screen still uses them).
  it("keeps vui, chucmung and chuanbi as chao, khen and nghi", () => {
    const art = (pose: MascotPose) => renderToStaticMarkup(<Mascot pose={pose} />).replace(/data-mascot="[^"]*"/, "");
    expect(art("vui")).toBe(art("chao"));
    expect(art("chucmung")).toBe(art("khen"));
    expect(art("chuanbi")).toBe(art("nghi"));
    expect(art("chao")).not.toBe(art("cho"));
  });

  // Red when: the outline or the teal detail is a fixed colour (it must follow the surface), or the
  // sticker outline and the face change.
  it("takes its outline and teal from variables, and solid tone overrides them", () => {
    const page = renderToStaticMarkup(<Mascot pose="rong" />);
    expect(page).toContain("var(--mascot-line)");
    expect(page).toContain("var(--mascot-teal)");
    expect(page).not.toMatch(/(fill|stroke)="#(661738|08686c)"/);
    expect(page).not.toContain("--mascot-line:#441125");
    const solid = renderToStaticMarkup(<Mascot pose="rong" tone="solid" />);
    expect(solid).toContain("--mascot-line:#441125");
    expect(solid).toContain("--mascot-teal:#70c8cd");
  });

  // Red when: a pose loses its die-cut white edge (it would not read on the field or solid pink), or the
  // glyph grows a teal detail it does not have.
  it("every pose keeps the white die-cut edge, the glyph has no teal", () => {
    for (const pose of POSES) expect(renderToStaticMarkup(<Mascot pose={pose} />)).toContain('stroke="#ffffff"');
    expect(renderToStaticMarkup(<Mascot pose="glyph" />)).not.toContain("--mascot-teal");
    expect(renderToStaticMarkup(<Mascot pose="chao" />)).toContain("--mascot-teal");
  });

  // Red when: the art carries its own title or label (the mascot would be read out).
  it("has no accessible name of its own", () => {
    for (const pose of POSES) expect(renderToStaticMarkup(<Mascot pose={pose} />)).not.toMatch(/aria-label|<title|role="img"/);
  });

  // Red when: the mascot replaces the words of an empty state.
  it("EmptyState keeps its words beside the mascot", () => {
    const markup = renderToStaticMarkup(<EmptyState mascot="cho" title="Chưa có tài liệu." hint="Tải lên." />);
    expect(markup).toContain("Chưa có tài liệu.");
    expect(markup).toContain('data-mascot="cho"');
  });
});
