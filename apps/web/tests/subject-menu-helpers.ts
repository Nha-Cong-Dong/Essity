// DESIGN-V4: a subject row's "Sửa" and "Xóa" now live in its "⋯" menu (Base UI), so a test opens the menu first.
import { act, fireEvent, screen } from "@testing-library/react";

/** Opens the "⋯" menu of a subject row. */
export async function openMenu(name: string) {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: `Tùy chọn môn ${name}` }));
  });
}

/** Opens the menu and picks "Sửa" or "Xóa" for that subject. */
export async function pick(verb: "Sửa" | "Xóa", name: string) {
  await openMenu(name);
  const item = await screen.findByRole("menuitem", { name: `${verb} ${name}` });
  await act(async () => {
    fireEvent.click(item);
  });
}
