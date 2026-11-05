"use client";

import { Dialog } from "@base-ui/react/dialog";

import { Button } from "@/components/ui/button";

// SESSION-END: the pop-up after "Kết thúc buổi học". A modal (Base UI Dialog: focus trap, Escape,
// aria-modal, title + description labelling). It praises the learner, says the cards are being made
// (the "đã vào Kho" toast still comes by itself), and offers the two ways on. Closing it (Escape)
// means "Về trang chủ": the session is already handed in, so there is nothing to stay for.

export const END_COPY = {
  title: "Bạn đã hoàn thành buổi học",
  praise: "Làm tốt lắm! Mỗi buổi ghi lại là một bước chắc hơn tới kỳ thi.",
  cards: "Thẻ kiến thức đang được chuẩn bị. Có thẻ mới, Essity sẽ báo và đưa vào Kho.",
  home: "Về trang chủ",
  more: "Học tiếp môn này",
} as const;

const POPUP =
  "fixed top-1/2 left-1/2 z-(--z-menu) flex max-h-[85vh] w-[min(92vw,32rem)] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 overflow-y-auto rounded-sheet bg-raised p-6 text-ink shadow-over";

export function SessionEndDialog({ open, onHome, onMore }: { open: boolean; onHome: () => void; onMore: () => void }) {
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) onHome();
      }}
    >
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-(--z-menu) bg-ink/40" />
        <Dialog.Popup className={POPUP}>
          <Dialog.Title className="m-0 font-display text-lead">{END_COPY.title}</Dialog.Title>
          <Dialog.Description className="m-0 text-body">{END_COPY.praise}</Dialog.Description>
          <p className="m-0 text-body text-ink-soft">{END_COPY.cards}</p>
          <div className="flex flex-col-reverse gap-2 min-[481px]:flex-row min-[481px]:justify-end">
            <Button type="button" variant="secondary" onClick={onHome}>
              {END_COPY.home}
            </Button>
            <Button type="button" onClick={onMore}>
              {END_COPY.more}
            </Button>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
