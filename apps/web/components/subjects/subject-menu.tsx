"use client";

import { Menu } from "@base-ui/react/menu";
import { MoreHorizontal } from "lucide-react";
import { forwardRef } from "react";

// DESIGN-V4 (mockups subjects.html): one "⋯" button per subject row, 44px round, holding "Sửa" and
// "Xóa" (Xóa still goes through its confirmation in the row). Base UI gives Esc to close, arrow keys
// and focus back to the button. The button is named "Tùy chọn môn <tên>"; the items keep the old
// names "Sửa <tên>" and "Xóa <tên>" so a screen reader says which subject.
const ITEM =
  "flex h-11 w-full items-center rounded-control px-3 text-left text-body font-medium text-ink outline-none data-[highlighted]:bg-sunken data-[highlighted]:outline-2 data-[highlighted]:-outline-offset-2 data-[highlighted]:outline-focus";

export const SubjectMenu = forwardRef<
  HTMLButtonElement,
  { name: string; onEdit: () => void; onDelete: () => void; describedBy?: string }
>(function SubjectMenu({ name, onEdit, onDelete, describedBy }, ref) {
  return (
    <Menu.Root>
      <Menu.Trigger
        ref={ref}
        aria-label={`Tùy chọn môn ${name}`}
        className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-block text-ink-soft hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        <MoreHorizontal aria-hidden="true" className="size-5" />
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner align="end" sideOffset={6} collisionPadding={8} className="z-(--z-menu)">
          <Menu.Popup className="z-(--z-menu) flex w-48 flex-col rounded-sheet bg-raised p-2 text-ink shadow-over">
            <Menu.Item className={ITEM} aria-label={`Sửa ${name}`} onClick={onEdit}>
              Sửa
            </Menu.Item>
            <Menu.Item className={ITEM} aria-label={`Xóa ${name}`} aria-describedby={describedBy} onClick={onDelete}>
              Xóa
            </Menu.Item>
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
});
