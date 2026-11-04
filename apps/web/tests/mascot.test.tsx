import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { EmptyState } from "@/components/empty-state";
import { Mascot, type MascotPose } from "@/components/mascot";

const POSES: MascotPose[] = ["vui", "cho", "chuanbi", "chucmung"];

describe("Mascot (phase B)", () => {
  // Red when: a pose is missing, or the mascot is announced to a screen reader.
  it.each(POSES)("%s is decoration: aria-hidden and a data-mascot mark", (pose) => {
    const markup = renderToStaticMarkup(<Mascot pose={pose} />);
    expect(markup).toContain('aria-hidden="true"');
    expect(markup).toContain(`data-mascot="${pose}"`);
  });

  // Red when: the mascot replaces the words of an empty state.
  it("EmptyState keeps its words beside the mascot", () => {
    const markup = renderToStaticMarkup(<EmptyState mascot="cho" title="Chưa có tài liệu." hint="Tải lên." />);
    expect(markup).toContain("Chưa có tài liệu.");
    expect(markup).toContain('data-mascot="cho"');
  });
});
