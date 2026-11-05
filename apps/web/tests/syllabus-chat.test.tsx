// @vitest-environment jsdom
// E3: the outline chat shows core-api's Vietnamese reply under the input and refreshes on a change.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { OutlineChat } from "@/components/syllabus/syllabus-chat";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function reply(body: unknown, ok = true) {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok, status: ok ? 200 : 500, json: async () => body })));
}

// Red when: the reply is not shown, or an applied change does not tell the screen to read again.
it("shows the reply and refreshes after an applied change", async () => {
  reply({ status: "applied", reply: "Đã gộp 2 phần thành “1.2”." });
  const changed = vi.fn();
  render(<OutlineChat subjectId="9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b" onChanged={changed} />);
  fireEvent.change(screen.getByLabelText(/Nói điều bạn muốn sửa/), { target: { value: "gộp phần 1.2 với 1.3" } });
  fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
  await waitFor(() => expect(screen.getByText(/Đã gộp 2 phần/)).toBeTruthy());
  expect(changed).toHaveBeenCalledTimes(1);
});

it("shows a hint without refreshing when nothing changed", async () => {
  reply({ status: "unclear", reply: "Mình chưa hiểu ý bạn." });
  const changed = vi.fn();
  render(<OutlineChat subjectId="9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b" onChanged={changed} />);
  fireEvent.change(screen.getByLabelText(/Nói điều bạn muốn sửa/), { target: { value: "ừ" } });
  fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
  await waitFor(() => expect(screen.getByText(/chưa hiểu/)).toBeTruthy());
  expect(changed).not.toHaveBeenCalled();
});

it("says so when the call fails", async () => {
  reply({}, false);
  render(<OutlineChat subjectId="9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b" onChanged={() => undefined} />);
  fireEvent.change(screen.getByLabelText(/Nói điều bạn muốn sửa/), { target: { value: "bỏ chương 5" } });
  fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
  await waitFor(() => expect(screen.getByText(/Chưa gửi được/)).toBeTruthy());
});

// Red when: the reply promises "Hoàn tác" but the chat has no such button (QA 05/11).
it("offers Hoàn tác for a change that can be undone, and calls the undo route", async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ status: "applied", reply: "Đã bỏ 1 mục. Bấm Hoàn tác nếu bạn đổi ý.", command_id: "c1" }) })
    .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ status: "undone" }) });
  vi.stubGlobal("fetch", fetcher);
  const changed = vi.fn();
  render(<OutlineChat subjectId="9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b" onChanged={changed} />);
  fireEvent.change(screen.getByLabelText(/Nói điều bạn muốn sửa/), { target: { value: "bỏ chương 5" } });
  fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
  fireEvent.click(await screen.findByRole("button", { name: "Hoàn tác" }));
  await waitFor(() => expect(screen.getByText("Đã hoàn tác.")).toBeTruthy());
  expect(fetcher.mock.calls[1][0]).toBe("/api/commands/c1/undo");
  expect(changed).toHaveBeenCalledTimes(2);
  expect(screen.queryByRole("button", { name: "Hoàn tác" })).toBeNull();
  // QA 05/11: focus returns to the input once the button is gone.
  expect(document.activeElement).toBe(screen.getByLabelText(/Nói điều bạn muốn sửa/));
});

it("keeps the Hoàn tác button outside the live region", async () => {
  reply({ status: "applied", reply: "Đã bỏ 1 mục.", command_id: "c1" });
  render(<OutlineChat subjectId="9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b" onChanged={() => undefined} />);
  fireEvent.change(screen.getByLabelText(/Nói điều bạn muốn sửa/), { target: { value: "bỏ chương 5" } });
  fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
  const undo = await screen.findByRole("button", { name: "Hoàn tác" });
  expect(undo.closest("[aria-live]")).toBeNull();
});

it("shows no Hoàn tác when the change has no command to undo", async () => {
  reply({ status: "applied", reply: "Đã gộp 2 mục.", command_id: null });
  render(<OutlineChat subjectId="9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b" onChanged={() => undefined} />);
  fireEvent.change(screen.getByLabelText(/Nói điều bạn muốn sửa/), { target: { value: "gộp" } });
  fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
  await waitFor(() => expect(screen.getByText(/Đã gộp 2 mục/)).toBeTruthy());
  expect(screen.queryByRole("button", { name: "Hoàn tác" })).toBeNull();
});
