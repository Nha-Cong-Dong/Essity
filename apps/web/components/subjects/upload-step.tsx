"use client";

import { useCallback, useState } from "react";

import { CreateFrame } from "@/components/subjects/create-steps";
import { Uploader } from "@/components/subjects/uploader";
import { Button } from "@/components/ui/button";
import type { Role } from "@/lib/syllabus/roles";

// H2: three tabs, one per kind of material. The tab fixes the role of the files put in it, so the
// learner never has to pick a role afterwards. Every tab stays mounted: switching keeps uploads
// running and only swaps the dropzone and that tab's own list of files.
// V14: the way into the subject is one button of the screen, outside the tabs.
const TABS: { role: Role; label: string }[] = [
  { role: "main", label: "Giáo trình chính" },
  { role: "supplementary", label: "Giáo trình phụ" },
  { role: "bank", label: "Bộ câu hỏi" },
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
  // DESIGN-V4: only the title, the subject's name and the step; no instructions, no outline preview.
  return (
    <CreateFrame current={2} subject={name}>
      <section aria-label="Tải tài liệu" className="flex flex-col gap-4">
        <div role="tablist" aria-label="Loại tài liệu" className="flex gap-1 overflow-x-auto rounded-full bg-block p-1">
          {TABS.map((t) => (
            <button
              key={t.role}
              type="button"
              role="tab"
              id={`tab-${t.role}`}
              aria-selected={tab === t.role}
              aria-controls={`panel-${t.role}`}
              onClick={() => setTab(t.role)}
              className={`min-h-11 shrink-0 rounded-full px-4 text-body whitespace-nowrap ${
                tab === t.role ? "bg-sheet font-semibold text-ink inset-ring-1 inset-ring-line" : "font-medium text-ink-soft"
              }`}
            >
              {t.label}
              {tally[t.role].done > 0 ? ` (${tally[t.role].done})` : ""}
            </button>
          ))}
        </div>
        {TABS.map((t) => (
          <div key={t.role} role="tabpanel" id={`panel-${t.role}`} aria-labelledby={`tab-${t.role}`} hidden={tab !== t.role}>
            <Uploader subjectId={subjectId} hasMain={hasMain} fixedRole={t.role} onCount={handlers[t.role]} />
          </div>
        ))}
        <div className="flex justify-end pt-2 max-[1023px]:sticky max-[1023px]:bottom-0 max-[1023px]:bg-sheet max-[1023px]:py-3">{enter}</div>
      </section>
    </CreateFrame>
  );
}
