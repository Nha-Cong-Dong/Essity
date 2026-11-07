// @vitest-environment jsdom
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HeadMascot } from "@/components/head-mascot";

describe("HeadMascot", () => {
  it("renders one decorative mascot with the given pose", () => {
    const { container } = render(<HeadMascot pose="chao" />);
    const svgs = container.querySelectorAll("svg[data-mascot]");
    expect(svgs).toHaveLength(1);
    expect(svgs[0].getAttribute("data-mascot")).toBe("chao");
    expect(svgs[0].getAttribute("aria-hidden")).toBe("true");
  });
});
