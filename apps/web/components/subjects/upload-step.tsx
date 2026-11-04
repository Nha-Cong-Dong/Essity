"use client";

import { useCallback, useState } from "react";

import { AUTH_LINK } from "@/components/auth/fields";
import { Mascot } from "@/components/mascot";
import { StepIndicator } from "@/components/subjects/step-indicator";
import { Uploader } from "@/components/subjects/uploader";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import type { Role } from "@/lib/syllabus/roles";

// H2: three tabs, one per kind of material. The tab fixes the role of the files put in it, so the
// learner never has to pick a role afterwards. Every tab stays mounted: switching keeps uploads
// running and only swaps the dropzone and that tab's own list of files.
// V14: the way into the subject is one button of the screen, outside the tabs.
const TABS: { role: Role; label: string; hint: string }[] = [
  { role: "main", label: "Giáo trình chính", hint: "Một giáo trình chính cho mỗi môn. Đề cương và thẻ kiến thức được dựng từ file này." },
  { role: "supplementary", label: "Giáo trình phụ", hint: "Slide, vở ghi, tài liệu tham khảo dạng PDF. Dùng để bổ sung ý và tìm nguồn." },
  { role: "bank", label: "Bộ câu hỏi", hint: "Đề thi, bài tập có sẵn. App tách câu hỏi và gợi ý dạng câu để luyện tập." },
];

type Tally = { done: number; running: number };
const NONE: Tally = { done: 0, running: 0 };

export function UploadStep({ name, subjectId, hasMain = true }: { name: string; subjectId: string; hasMain?: boolean }) {
  const [tab, setTab] = useState<Role>("main");
  const [tally, setTally] = useState<Record<Role, Tally>>({ main: NONE, supplementary: NONE, bank: NONE });
  const set = useCallback(
    (role: Role, done: number, running: number) =>
      setTally((all) => (all[role].done === done && all[role].running === running ? all : { ...all, [role]: { done, running } })),
    [],
  );
  const onMain = useCallback((d: number, r: number) => set("main", d, r), [set]);
  const onSupp = useCallback((d: number, r: number) => set("supplementary", d, r), [set]);
  const onBank = useCallback((d: number, r: number) => set("bank", d, r), [set]);
  const handlers: Record<Role, (d: number, r: number) => void> = { main: onMain, supplementary: onSupp, bank: onBank };
  const running = tally.main.running + tally.supplementary.running + tally.bank.running;
  const enter = (
    <Button
      size="lg"
      pending={running > 0}
      render={running > 0 ? undefined : <a href={`/subjects/${subjectId}`} />}
      className="max-[1023px]:w-full min-[1024px]:min-w-64"
    >
      Sẵn sàng học thôi!
    </Button>
  );
  return (
    <section aria-labelledby="upload-title" className="flex w-full max-w-220 flex-col gap-6">
      <a href="/subjects" className={AUTH_LINK}>
        Môn học
      </a>
      <StepIndicator current={2} />
      <Sheet className="p-5 sm:p-8">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 flex-col gap-2">
            <h1 id="upload-title" className="m-0 font-display text-title wrap-anywhere">
              Tải tài liệu cho {name}
            </h1>
            <p className="m-0 max-w-[56ch] text-read text-ink-soft">
              Câu hỏi và thẻ sẽ dựa trên đúng những trang này. Chọn loại tài liệu ở các tab bên dưới.
            </p>
          </div>
          <div className="hidden shrink-0 min-[641px]:block">
            <Mascot pose="chuanbi" size="sm" />
          </div>
        </div>
        <div
          role="tablist"
          aria-label="Loại tài liệu"
          className="mt-6 flex gap-1 overflow-x-auto rounded-full bg-sunken p-1"
        >
          {TABS.map((t) => (
            <button
              key={t.role}
              type="button"
              role="tab"
              id={`tab-${t.role}`}
              aria-selected={tab === t.role}
              aria-controls={`panel-${t.role}`}
              onClick={() => setTab(t.role)}
              className={`min-h-11 shrink-0 rounded-full px-4 text-read whitespace-nowrap ${
                tab === t.role ? "bg-sheet font-semibold text-ink shadow-sheet" : "font-medium text-ink-soft"
              }`}
            >
              {t.label}
              {tally[t.role].done > 0 ? ` (${tally[t.role].done})` : ""}
            </button>
          ))}
        </div>
        {TABS.map((t) => (
          <div key={t.role} role="tabpanel" id={`panel-${t.role}`} aria-labelledby={`tab-${t.role}`} hidden={tab !== t.role}>
            <p className="mt-4 mb-0 max-w-[56ch] text-read text-ink-soft">{t.hint}</p>
            <Uploader subjectId={subjectId} hasMain={hasMain} fixedRole={t.role} onCount={handlers[t.role]} />
          </div>
        ))}
        <div className="mt-8 flex justify-end max-[1023px]:sticky max-[1023px]:bottom-0 max-[1023px]:bg-sheet max-[1023px]:py-3">{enter}</div>
      </Sheet>
    </section>
  );
}
