"use client";

import { useRef } from "react";

import { Dialog } from "@base-ui/react/dialog";

import { Mascot } from "@/components/mascot";
import { Button } from "@/components/ui/button";

// SESSION-END: the pop-up after "Kết thúc buổi học". A modal (Base UI Dialog: focus trap, Escape,
// aria-modal, title + description labelling). It praises the learner, says the cards are being made
// (the "đã vào Kho" toast still comes by itself), and offers the two ways on. Closing it (Escape)
// means "Về trang chủ": the session is already handed in, so there is nothing to stay for.

export const END_COPY = {
  title: "Làm tốt lắm!",
  praise: "Thẻ của buổi này đang được chuẩn bị, xong sẽ báo bạn.",
  /** `n` pieces were kept in this session. */
  recorded: (n: number) => `Bạn đã ghi lại ${n} lần, thẻ đang được chuẩn bị. Xong sẽ báo bạn.`,
  emptyTitle: "Buổi này chưa có ghi chép",
  emptyText: "Bạn chưa ghi lại phần nào nên chưa có thẻ nào được tạo. Lần sau cứ ghi vài dòng là đủ.",
  home: "Về trang chủ",
  more: "Học tiếp môn này",
} as const;

// V4-SCREENS-B (mockup session-end): a plum band with Bé Trang cheering and four sparks that pop in
// one after another (transform and opacity only; none under reduced motion), a white lower half with
// the words and two equal buttons. Pointer outside does nothing.
const POPUP =
  "fixed top-1/2 left-1/2 z-(--z-menu) flex max-h-[90vh] w-[min(92vw,27.5rem)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-y-auto rounded-sheet border border-line bg-raised text-ink";
const SPARK =
  "absolute block size-6 bg-on-plum [clip-path:polygon(50%_0,62%_38%,100%_50%,62%_62%,50%_100%,38%_62%,0_50%,38%_38%)] motion-safe:animate-rise";

export function SessionEndDialog({
  open,
  empty = false,
  recorded,
  onHome,
  onMore,
}: {
  open: boolean;
  /** No piece was kept: nothing to praise, no cards coming. */
  empty?: boolean;
  /** How many times the learner pressed "Ghi lại" (or the typed text kept at the end). */
  recorded?: number;
  onHome: () => void;
  onMore: () => void;
}) {
  const home = useRef<HTMLButtonElement>(null);
  return (
    <Dialog.Root
      open={open}
      // Pointer outside does nothing; Escape is "Về trang chủ".
      disablePointerDismissal
      onOpenChange={(next, details) => {
        if (!next && details.reason === "escape-key") onHome();
      }}
    >
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-(--z-menu) bg-ink/60" />
        <Dialog.Popup className={POPUP} initialFocus={home}>
          <div data-tier="field" className="relative flex h-44 shrink-0 items-end justify-center overflow-hidden bg-plum">
            <Mascot pose={empty ? "cho" : "khen"} size="md" tone="solid" className="relative z-10" />
            {empty ? null : (
              <>
                <span aria-hidden="true" className={`${SPARK} top-6 left-[24%] size-8 [animation-delay:140ms]`} />
                <span aria-hidden="true" className={`${SPARK} top-4 right-[22%] size-7 bg-accent-bright [animation-delay:230ms]`} />
                <span aria-hidden="true" className={`${SPARK} top-20 right-[12%] size-5 [animation-delay:320ms]`} />
                <span aria-hidden="true" className={`${SPARK} top-24 left-[13%] size-4 bg-accent-bright [animation-delay:410ms]`} />
              </>
            )}
          </div>
          <div className="flex flex-col items-center gap-2.5 p-6 pb-7 text-center">
            <Dialog.Title className="m-0 font-display text-title text-balance">{empty ? END_COPY.emptyTitle : END_COPY.title}</Dialog.Title>
            <Dialog.Description className="m-0 text-body text-ink-soft text-balance">
              {empty ? END_COPY.emptyText : recorded && recorded > 0 ? END_COPY.recorded(recorded) : END_COPY.praise}
            </Dialog.Description>
            <div className="mt-3 grid w-full gap-3 min-[481px]:grid-cols-2">
              <Button ref={home} type="button" onClick={onHome}>
                {END_COPY.home}
              </Button>
              <Button type="button" variant="secondary" onClick={onMore}>
                {END_COPY.more}
              </Button>
            </div>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
