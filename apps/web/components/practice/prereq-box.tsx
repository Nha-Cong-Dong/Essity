"use client";

import { Dialog } from "@base-ui/react/dialog";
import Link from "next/link";
import { useState } from "react";

import { Markdown } from "@/components/markdown/markdown";
import { buttonVariants } from "@/components/ui/button";
import type { PrereqCard } from "@/lib/question-list-types";

// PRACTICE-PREREQ (user, 07/11): an unlocked question shows a small "Kiến thức nền" box with one
// chip per card that unlocked it. A chip opens that card's text in a side drawer (a bottom sheet
// on a phone). The drawer is a Base UI Dialog: focus is trapped, Esc, the X and the scrim close
// it, and focus returns to the chip. No cards -> no box. Copy is the Coder's.

const CHIP =
  "min-h-11 max-w-full min-w-0 inline-flex items-center rounded-full bg-sheet px-4 py-2 text-left text-meta font-medium text-ink wrap-anywhere inset-ring-1 inset-ring-line-strong hover:bg-sunken outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

export function PrereqBox({ cards, vaultHref = "/kho-kien-thuc" }: { cards: PrereqCard[]; vaultHref?: string }) {
  const [openId, setOpenId] = useState<string | null>(null);
  if (cards.length === 0) return null;
  const card = cards.find((c) => c.id === openId) ?? null;

  return (
    <section aria-labelledby="prereq-title" data-prereq-box className="rounded-tile bg-sunken p-4 sm:p-5">
      <h2 id="prereq-title" className="m-0 text-meta font-semibold text-ink-soft">
        Kiến thức nền
      </h2>
      <ul className="m-0 mt-3 flex list-none flex-wrap gap-2 p-0">
        {cards.map((c) => (
          <li key={c.id} className="min-w-0 max-w-full">
            <button type="button" data-user className={CHIP} onClick={() => setOpenId(c.id)}>
              {c.title}
            </button>
          </li>
        ))}
      </ul>
      <Dialog.Root open={card !== null} onOpenChange={(open) => !open && setOpenId(null)}>
        <Dialog.Portal>
          <Dialog.Backdrop className="fixed inset-0 z-(--z-scrim) bg-ink/40 transition-opacity duration-(--dur-ui) data-[ending-style]:opacity-0 data-[starting-style]:opacity-0 motion-reduce:duration-1" />
          <Dialog.Popup
            data-prereq-drawer
            className="fixed z-(--z-panel) flex flex-col bg-raised text-ink shadow-over outline-none inset-x-0 bottom-0 max-h-[85dvh] rounded-t-sheet min-[641px]:inset-x-auto min-[641px]:inset-y-0 min-[641px]:right-0 min-[641px]:max-h-none min-[641px]:w-[420px] min-[641px]:rounded-t-none min-[641px]:rounded-l-sheet transition-transform duration-(--dur-reveal) ease-(--ease-out) data-[ending-style]:translate-y-full data-[starting-style]:translate-y-full min-[641px]:data-[ending-style]:translate-x-full min-[641px]:data-[starting-style]:translate-x-full min-[641px]:data-[ending-style]:translate-y-0 min-[641px]:data-[starting-style]:translate-y-0 motion-reduce:transition-none"
          >
            <div className="flex items-start gap-3 border-b border-line p-5">
              <div className="min-w-0 flex-1">
                <p className="m-0 text-meta text-ink-soft">Kiến thức nền</p>
                <Dialog.Title data-user className="m-0 mt-1 font-display text-lead wrap-anywhere">
                  {card?.title}
                </Dialog.Title>
              </div>
              <Dialog.Close
                aria-label="Đóng"
                className="inline-flex size-11 shrink-0 items-center justify-center rounded-full text-ink hover:bg-sunken outline-none focus-visible:outline-2 focus-visible:outline-focus"
              >
                <span aria-hidden="true" className="text-lead leading-none">
                  ×
                </span>
              </Dialog.Close>
            </div>
            <Dialog.Description className="sr-only">Nội dung thẻ kiến thức nền.</Dialog.Description>
            <div data-user className="min-h-0 flex-1 overflow-y-auto p-5">
              <Markdown className="text-body" text={card?.summary ?? ""} />
            </div>
            <div className="border-t border-line p-5">
              <Link href={vaultHref} className={buttonVariants({ variant: "secondary", className: "w-full" })}>
                Mở trong Kho
              </Link>
            </div>
          </Dialog.Popup>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  );
}
