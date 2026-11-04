"use client";

import { useCallback, useState } from "react";

import { AUTH_LINK } from "@/components/auth/fields";
import { Mascot } from "@/components/mascot";
import { Uploader } from "@/components/subjects/uploader";
import { Button } from "@/components/ui/button";
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

export function UploadStep({ name, subjectId, hasMain = true }: { name: string; subjectId: string; hasMain?: boolean }) {
  const [tab, setTab] = useState<Role>("main");
  const [counts, setCounts] = useState<Record<Role, number>>({ main: 0, supplementary: 0, bank: 0 });
  const total = counts.main + counts.supplementary + counts.bank;
  const onMain = useCallback((n: number) => setCounts((all) => (all.main === n ? all : { ...all, main: n })), []);
  const onSupp = useCallback((n: number) => setCounts((all) => (all.supplementary === n ? all : { ...all, supplementary: n })), []);
  const onBank = useCallback((n: number) => setCounts((all) => (all.bank === n ? all : { ...all, bank: n })), []);
  const handlers: Record<Role, (n: number) => void> = { main: onMain, supplementary: onSupp, bank: onBank };
  return (
    <section aria-labelledby="upload-title" className="flex w-full max-w-220 flex-col gap-6">
      <a href="/subjects" className={AUTH_LINK}>
        Môn học
      </a>
      <header className="flex items-end justify-between gap-4">
        <div className="flex flex-col gap-2">
          <p className="m-0 text-small font-semibold text-ink-soft">Bước 2 trên 2</p>
          <h1 id="upload-title" className="m-0 font-display text-title">
            Tải tài liệu cho {name}
          </h1>
          <p className="m-0 max-w-[56ch] text-read text-ink-soft">
            Câu hỏi và thẻ sẽ dựa trên đúng những trang này. Chọn loại tài liệu ở các tab bên dưới.
          </p>
        </div>
        <Mascot pose="chuanbi" size="sm" />
      </header>
      <div className="rounded-sheet bg-sunken p-6 max-[480px]:p-4">
        <div role="tablist" aria-label="Loại tài liệu" className="flex flex-wrap gap-2">
          {TABS.map((t) => (
            <button
              key={t.role}
              type="button"
              role="tab"
              id={`tab-${t.role}`}
              aria-selected={tab === t.role}
              aria-controls={`panel-${t.role}`}
              onClick={() => setTab(t.role)}
              className={`min-h-11 rounded-control px-4 text-read font-medium ${
                tab === t.role ? "bg-rose-100 font-semibold text-ink" : "text-ink-soft"
              }`}
            >
              {t.label}
              {counts[t.role] > 0 ? ` (${counts[t.role]})` : ""}
            </button>
          ))}
        </div>
        {TABS.map((t) => (
          <div key={t.role} role="tabpanel" id={`panel-${t.role}`} aria-labelledby={`tab-${t.role}`} hidden={tab !== t.role}>
            <p className="mt-4 mb-0 max-w-[56ch] text-read text-ink-soft">{t.hint}</p>
            <Uploader subjectId={subjectId} hasMain={hasMain} fixedRole={t.role} onCount={handlers[t.role]} />
          </div>
        ))}
      </div>
      <div className="flex flex-col items-start gap-2">
        {total > 0 ? (
          <Button render={<a href={`/subjects/${subjectId}/syllabus`} />}>Sẵn sàng học thôi!</Button>
        ) : (
          <>
            <Button type="button" disabled aria-describedby="ready-why">
              Sẵn sàng học thôi!
            </Button>
            <span id="ready-why" className="text-small text-ink-soft">
              Tải ít nhất một tài liệu để bắt đầu.
            </span>
          </>
        )}
      </div>
    </section>
  );
}
