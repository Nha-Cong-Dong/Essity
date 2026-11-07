// @vitest-environment jsdom
// PREDEPLOY-FIX-A E-03 (React #418 on /subjects/[id]/syllabus): CommandLive's portal filled the
// slot while the page around it was still hydrating. The slot is `data-pending` until its own
// component hydrated; CommandLive waits for that.
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), usePathname: () => "/subjects/x/syllabus" }));

import { CommandLive } from "@/components/command-live";
import { CommandSlot } from "@/components/command-slot";

const ID = "31111111-2222-4333-8444-555555555555";

beforeEach(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query }));
  document.body.innerHTML = "";
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("E-03 command slot", () => {
  it("E-03 the server HTML of the slot is pending and keeps its selector attributes", () => {
    const html = renderToString(<CommandSlot bottom />);
    expect(html).toContain("data-command-slot-bottom");
    expect(html).toContain('data-pending="true"');
  });

  it("E-03 CommandLive does not fill a slot that is still pending", async () => {
    document.body.insertAdjacentHTML("beforeend", '<div data-command-slot-bottom data-pending="true"></div>');
    render(<CommandLive subjectId={ID} />, { container: document.body.appendChild(document.createElement("div")) });
    await act(async () => undefined);
    expect(document.querySelector("[data-command-slot-bottom] [data-syllabus-chat]")).toBeNull();
    // The slot component hydrated: the mark goes and the chat is drawn into it.
    await act(async () => {
      document.querySelector("[data-command-slot-bottom]")?.removeAttribute("data-pending");
    });
    await waitFor(() => expect(document.querySelector("[data-command-slot-bottom] [data-syllabus-chat]")).not.toBeNull());
  });

  it("E-03 a mounted CommandSlot drops data-pending (client effect)", async () => {
    render(<CommandSlot />);
    await act(async () => undefined);
    const slot = document.querySelector("[data-command-slot]");
    expect(slot).not.toBeNull();
    expect(slot?.hasAttribute("data-pending")).toBe(false);
  });
});
