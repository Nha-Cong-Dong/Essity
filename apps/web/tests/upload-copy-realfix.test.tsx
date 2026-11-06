// @vitest-environment jsdom
// REALFIX 2, 3: upload copy matches what is accepted (PDF only); note-only card says photos are read after Save.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { ConfirmCard } from "@/components/confirm-card";
import { UploadStep } from "@/components/subjects/upload-step";

afterEach(cleanup);

it("upload step promises only PDFs", () => {
  render(<UploadStep name="MMT" subjectId="9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b" />);
  expect(screen.queryByText(/ảnh vở/)).toBeNull();
  expect((document.querySelector('input[type="file"]') as HTMLInputElement).accept).toContain("pdf");
});

it("note-only card tells the photo is read after Save, only with a photo", () => {
  const card = { card: "note_only", ranges: [], studied_on: null } as never;
  render(<ConfirmCard card={card} saving={false} hasPhotos onSave={() => {}} onSentence={() => {}} onRanges={() => {}} />);
  expect(screen.getByText(/sau khi bạn bấm Lưu/)).toBeTruthy();
});

it("note-only card without a photo has no photo hint", () => {
  const card = { card: "note_only", ranges: [], studied_on: null } as never;
  render(<ConfirmCard card={card} saving={false} onSave={() => {}} onSentence={() => {}} onRanges={() => {}} />);
  expect(screen.queryByText(/sau khi bạn bấm Lưu/)).toBeNull();
});

// H2: three tabs, one per kind of material. Red when: a tab goes missing or switching shows two panels.
it("H2: has the three tabs and shows one panel at a time", async () => {
  const { fireEvent } = await import("@testing-library/react");
  render(<UploadStep name="MMT" subjectId="9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b" />);
  const names = screen.getAllByRole("tab").map((t) => t.textContent);
  expect(names).toEqual(["Giáo trình chính", "Giáo trình phụ", "Bộ câu hỏi"]);
  expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
  fireEvent.click(screen.getByRole("tab", { name: "Bộ câu hỏi" }));
  expect(screen.getByRole("tab", { name: "Bộ câu hỏi" }).getAttribute("aria-selected")).toBe("true");
  expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
});
