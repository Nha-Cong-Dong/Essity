import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { EmptyState } from "@/components/empty-state";
import { Mascot, type MascotPose } from "@/components/mascot";

const POSES: MascotPose[] = ["chao", "khen", "nghi", "cho", "rong", "glyph", "vui", "chucmung", "chuanbi"];

describe("Mascot (MASCOT-V3, cloud and sun)", () => {
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

  const KINDS = ["cloud", "sun"] as const;

  // Red when: a kind or pose is missing, or the default stops being the cloud (every older call site relies on it).
  it.each(KINDS)("%s: every pose draws, is marked with its kind and keeps the white die-cut edge", (kind) => {
    for (const pose of POSES) {
      const markup = renderToStaticMarkup(<Mascot kind={kind} pose={pose} />);
      expect(markup).toContain(`data-mascot-kind="${kind}"`);
      expect(markup).toContain('stroke="#ffffff"');
    }
    expect(renderToStaticMarkup(<Mascot pose="chao" />)).toContain('data-mascot-kind="cloud"');
  });

  // Red when: the two mascots are the same drawing, or a pose of one kind equals its other pose.
  it("the cloud and the sun are different drawings, pose by pose", () => {
    const art = (kind: "cloud" | "sun", pose: MascotPose) =>
      renderToStaticMarkup(<Mascot kind={kind} pose={pose} />).replace(/data-mascot[a-z-]*="[^"]*"/g, "");
    for (const pose of POSES) expect(art("cloud", pose)).not.toBe(art("sun", pose));
    expect(art("sun", "chao")).not.toBe(art("sun", "khen"));
  });

  // Red when: the teal detail leaks into a glyph, or a pose loses it.
  it("only the glyph has no teal detail", () => {
    for (const kind of KINDS) {
      expect(renderToStaticMarkup(<Mascot kind={kind} pose="glyph" />)).not.toContain("--mascot-teal");
      expect(renderToStaticMarkup(<Mascot kind={kind} pose="chao" />)).toContain("--mascot-teal");
    }
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
