"use client";

import { Dialog } from "@base-ui/react/dialog";
import { useState } from "react";

import { SubjectMark } from "@/components/subject-mark";
import { Button } from "@/components/ui/button";
import { studyHref } from "@/lib/session-study/entry";
import { paceLine, TODAY_V2_COPY as COPY, type LearnItem } from "@/lib/today-v2";

// Hackathon 04/11 (C4, C5): "Xem tất cả" opens one horizontal card per subject; "Hướng dẫn học"
// opens a few slides on how to learn with Essity. Both are plain modals (Base UI Dialog: Esc, focus trap).

const POPUP =
  "fixed top-1/2 left-1/2 z-(--z-menu) flex max-h-[85vh] w-[min(92vw,40rem)] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 overflow-y-auto rounded-sheet bg-raised p-6 text-ink shadow-over";
const BACKDROP = "fixed inset-0 z-(--z-menu) bg-ink/40";

// V10: the four steps of a study session, in the words the product owner gave.
const STEPS = [
  { title: "B1", body: "Vào giao diện buổi học." },
  { title: "B2", body: "Học bài theo nội dung định hướng theo đề cương." },
  {
    title: "B3",
    body: "Mỗi phiên của buổi học, trước khi tạm nghỉ thì ghi lại những nội dung mình đã học vào phần \"Bạn đã học gì\" rồi bấm Ghi lại để hệ thống ghi lại; có thể gửi kèm vở ghi, slide hay tài liệu.",
  },
  { title: "B4", body: "Khi nào học xong rồi thì bấm Hoàn thành để kết thúc buổi học." },
] as const;

type Next = Extract<LearnItem, { state: "next" }>;

function SubjectRow({ item }: { item: LearnItem }) {
  const [open, setOpen] = useState(false);
  const id = `all-${item.subject.id}`;
  const next = item.state === "next" ? (item as Next) : null;
  return (
    <li className="rounded-tile bg-sunken p-4">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen(!open)}
          className="flex min-w-0 flex-1 basis-40 items-center gap-3 text-left text-section font-semibold wrap-anywhere"
        >
          <SubjectMark name={item.subject.name} />
          <span className="min-w-0">
            {item.subject.name}
            <span className="block text-meta font-normal text-ink-soft">
              {open ? "Bấm để thu gọn" : "Bấm để xem nội dung cụ thể"} {open ? "▴" : "▾"}
            </span>
          </span>
        </button>
        {next && (
          <Button
            render={<a href={studyHref(item.subject.id, next.section.id)} />}
            nativeButton={false}
            variant="secondary"
            aria-label={`${COPY.studyNow} · ${item.subject.name}`}
          >
            {COPY.studyNow}
          </Button>
        )}
      </div>
      {open && (
        <div id={id} className="mt-3 text-read wrap-anywhere">
          {next ? (
            <>
              <p className="m-0">
                {next.section.chapter ? `${next.section.chapter} · ` : ""}Phần {next.section.label} {next.section.title}
                {next.section.pages ? ` · ${next.section.pages}` : ""}
              </p>
              <p className="m-0 text-meta text-ink-soft">{paceLine(next.pace)}</p>
            </>
          ) : item.state === "finished" ? (
            <p className="m-0">{COPY.finished}</p>
          ) : (
            <p className="m-0">{COPY.emptyReason.no_textbook}</p>
          )}
        </div>
      )}
    </li>
  );
}

function Shell({
  trigger,
  title,
  children,
  primary = false,
}: {
  trigger: string;
  title: string;
  children: React.ReactNode;
  primary?: boolean;
}) {
  return (
    <Dialog.Root>
      <Dialog.Trigger render={<Button variant={primary ? "primary" : "secondary"} />}>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Backdrop className={BACKDROP} />
        <Dialog.Popup className={POPUP}>
          <Dialog.Title className="m-0 font-display text-lead">{title}</Dialog.Title>
          {children}
          <div className="flex justify-end">
            <Dialog.Close render={<Button variant="secondary" />}>{COPY.close}</Dialog.Close>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Guide() {
  const [step, setStep] = useState(0);
  const last = STEPS.length - 1;
  const current = STEPS[step];
  return (
    <div className="flex flex-col gap-3" aria-live="polite">
      <p className="m-0 text-meta text-ink-soft">
        Bước {step + 1} / {STEPS.length}
      </p>
      <div className="rounded-tile bg-rose-100 p-6">
        <h3 className="m-0 text-section font-semibold">{current.title}</h3>
        <p className="m-0 mt-2 text-read">{current.body}</p>
      </div>
      <div className="flex justify-between">
        <Button variant="quiet" disabled={step === 0} onClick={() => setStep(step - 1)}>
          Trước
        </Button>
        <Button variant="quiet" disabled={step === last} onClick={() => setStep(step + 1)}>
          Tiếp
        </Button>
      </div>
    </div>
  );
}

export function LearnActions({ items, primary = false }: { items: LearnItem[]; primary?: boolean }) {
  return (
    <div className="mt-6 flex flex-wrap gap-3">
      {items.length > 0 && (
        <Shell trigger={COPY.seeAll} title={COPY.learn} primary={primary}>
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {items.map((item) => (
              <SubjectRow key={item.subject.id} item={item} />
            ))}
          </ul>
        </Shell>
      )}
      <Shell trigger={COPY.guide} title={COPY.guide}>
        <Guide />
      </Shell>
    </div>
  );
}
