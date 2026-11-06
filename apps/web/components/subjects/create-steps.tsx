import { Check } from "lucide-react";
import type { ReactNode } from "react";

import { FieldGrain } from "@/components/today-v2/field-art";
import { PageColumn } from "@/components/shells";
import { BackLink } from "@/components/screen-kit";
import { cn } from "@/lib/utils";

// DESIGN-V4 (mockups subject-new.html): "Tạo môn" is a title, a white form sheet (7/12) and the field
// column with the three steps (5/12). No instructions: the steps are the only words. Under 1024px the
// step column becomes a slim strip above the form.
const STEPS = ["Thông tin môn", "Giáo trình", "Đề cương"] as const;

export function CreateSteps({ current, className }: { current: 1 | 2 | 3; className?: string }) {
  return (
    <aside
      aria-label="Các bước tạo môn"
      className={cn(
        "relative isolate flex min-w-0 flex-col gap-4 overflow-hidden rounded-tile bg-field p-4 text-on-plum min-[1024px]:gap-6 min-[1024px]:p-8",
        className,
      )}
    >
      <FieldGrain />
      <p className="m-0 hidden font-display text-lead min-[1024px]:block">Các bước</p>
      <ol className="m-0 flex list-none justify-between gap-2 p-0 min-[1024px]:flex-col min-[1024px]:justify-start min-[1024px]:gap-0">
        {STEPS.map((label, index) => {
          const n = index + 1;
          const done = n < current;
          const now = n === current;
          return (
            <li
              key={label}
              aria-current={now ? "step" : undefined}
              className={cn(
                "relative flex min-w-0 flex-1 flex-col items-center gap-1.5 text-center text-chip font-semibold min-[1024px]:min-h-24 min-[1024px]:flex-none min-[1024px]:flex-row min-[1024px]:gap-4 min-[1024px]:text-left min-[1024px]:font-display min-[1024px]:text-lead min-[1024px]:leading-tight",
                now ? "text-on-plum" : "text-on-plum-soft",
                // the line between two steps (vertical on desktop)
                n < STEPS.length &&
                  "min-[1024px]:before:absolute min-[1024px]:before:top-[4.25rem] min-[1024px]:before:bottom-[-1.5rem] min-[1024px]:before:left-[1.3rem] min-[1024px]:before:w-0.5 min-[1024px]:before:bg-on-plum-soft/40 min-[1024px]:before:content-['']",
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  "grid size-9 shrink-0 place-items-center rounded-full font-display text-meta font-bold min-[1024px]:size-11 min-[1024px]:text-lead",
                  done && "bg-on-plum-soft text-field",
                  now && "bg-on-plum text-field",
                  !done && !now && "text-on-plum inset-ring-2 inset-ring-on-plum-soft",
                )}
              >
                {done ? <Check className="size-5" strokeWidth={3} /> : n}
              </span>
              <span>{label}</span>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}

/** The frame of both steps: back link, title, the step's own sheet, the steps. */
export function CreateFrame({ current, subject, children }: { current: 1 | 2; subject?: string; children: ReactNode }) {
  return (
    <PageColumn width="full" className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <BackLink href="/subjects">Quay lại</BackLink>
        <h1 className="m-0 font-display text-title">Tạo môn</h1>
        {subject ? <p className="m-0 text-body text-ink-soft break-words">{subject}</p> : null}
      </header>
      <div className="grid gap-5 min-[1024px]:grid-cols-12">
        <div className="min-w-0 rounded-tile bg-sheet p-6 shadow-sheet min-[1024px]:col-span-7 min-[1024px]:p-9">
          {children}
        </div>
        <CreateSteps current={current} className="max-[1023px]:order-first min-[1024px]:col-span-5" />
      </div>
    </PageColumn>
  );
}
