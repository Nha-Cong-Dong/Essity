// @vitest-environment jsdom
// Q14 (QA 05/11): deleting a card in the Kho asks first, in the page; "Giữ thẻ" keeps it.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CardList } from "@/components/vault/card-list";

const CARD = { id: "c1", title: "TCP", content: "Bắt tay ba bước", kind: "concept", anchors: [] };
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("vault card delete", () => {
  it("does not call the API on the first click, asks, then deletes on confirm", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<CardList cards={[CARD]} />);
    fireEvent.click(screen.getByRole("button", { name: "Sửa thẻ" }));
    fireEvent.click(screen.getByRole("button", { name: "Xóa thẻ" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("group", { name: "Xác nhận xóa thẻ" })).toBeTruthy();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Xóa hẳn thẻ" })));
    expect(fetchMock).toHaveBeenCalledWith("/api/vault/cards/c1", { method: "DELETE" });
    expect(screen.queryByText("TCP")).toBeNull();
  });

  it("Giữ thẻ closes the question and keeps the card", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<CardList cards={[CARD]} />);
    fireEvent.click(screen.getByRole("button", { name: "Sửa thẻ" }));
    fireEvent.click(screen.getByRole("button", { name: "Xóa thẻ" }));
    fireEvent.click(screen.getByRole("button", { name: "Giữ thẻ" }));
    expect(screen.queryByRole("group", { name: "Xác nhận xóa thẻ" })).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Tiêu đề thẻ")).toBeTruthy();
  });
});
