// @vitest-environment jsdom
// C2-SYLLABUS-V4: the Đề cương screen is built from the v4 blocks (field totals, white sheet tree,
// mascot empty and error states, BackLink). Behaviour is covered by syllabus-screen.test.tsx.
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SyllabusScreen } from "@/components/syllabus/syllabus-screen";

afterEach(cleanup);

describe("Đề cương on v4 blocks", () => {
  it("ready: one plum field (totals), the tree in a white sheet, a back arrow link", () => {
    const { container } = render(<SyllabusScreen state="ready" />);
    expect(container.querySelectorAll("[data-tier='field']")).toHaveLength(1);
    expect(container.querySelector("[data-tier='field'] [data-totals]")).not.toBeNull();
    expect(container.querySelector("[data-nx][data-tier='sheet']")).not.toBeNull();
    expect(container.querySelector("a svg")).not.toBeNull();
  });

  it.each(["empty-no-main", "error"] as const)("%s: a sheet with the mascot empty state and one action", (state) => {
    const { container } = render(<SyllabusScreen state={state} />);
    expect(container.querySelector("[data-tier='sheet'] [data-slot='empty-state']")).not.toBeNull();
    expect(container.querySelector("[data-tier='field']")).toBeNull();
  });
});
