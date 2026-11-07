// @vitest-environment jsdom
// PREDEPLOY-FIX-A E-01: a 401 on a card edit keeps the form and its values and offers a sign-in link.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CardList } from "@/components/vault/card-list";
import { go } from "@/lib/navigate";

vi.mock("@/lib/navigate", () => ({ go: vi.fn() }));

const CARD = { id: "c1", title: "TCP", content: "Bắt tay ba bước", kind: "concept", anchors: [] };
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("E-01 vault 401", () => {
  it("E-01 saving with an expired session keeps the edit form and shows a login link, no redirect", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 401 })));
    render(<CardList cards={[CARD]} />);
    fireEvent.click(screen.getByRole("button", { name: "Sửa thẻ" }));
    fireEvent.change(screen.getByLabelText("Tiêu đề thẻ"), { target: { value: "TCP mới" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: /Lưu/ })));
    expect(screen.getByText("Phiên đăng nhập đã hết hạn.", { exact: false })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Đăng nhập lại" }).getAttribute("href")).toBe("/login");
    expect((screen.getByLabelText("Tiêu đề thẻ") as HTMLInputElement).value).toBe("TCP mới");
    expect(go).not.toHaveBeenCalled();
  });
});
