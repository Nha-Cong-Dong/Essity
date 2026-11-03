"use client";

import { useState } from "react";

import { Marker } from "@/components/notebook";
import { AUTH_LINK } from "@/components/auth/fields";
import { Uploader } from "@/components/subjects/uploader";
import { Sheet } from "@/components/ui/sheet";
import type { Role } from "@/lib/syllabus/roles";

// H2: three tabs, one per kind of material. The tab fixes the role of the files put in it, so the
// learner never has to pick a role afterwards. Every tab stays mounted: switching keeps uploads running.
const TABS: { role: Role; label: string; hint: string }[] = [
  { role: "main", label: "Giáo trình chính", hint: "Một giáo trình chính cho mỗi môn. Đề cương và thẻ kiến thức được dựng từ file này." },
  { role: "supplementary", label: "Giáo trình phụ", hint: "Slide, vở ghi, tài liệu tham khảo dạng PDF. Dùng để bổ sung ý và tìm nguồn." },
  { role: "bank", label: "Bộ câu hỏi", hint: "Đề thi, bài tập có sẵn. App tách câu hỏi và gợi ý dạng câu để luyện tập." },
];

export function UploadStep({ name, subjectId, hasMain = true }: { name: string; subjectId: string; hasMain?: boolean }) {
  const [tab, setTab] = useState<Role>("main");
  return (
    <Sheet className="relative w-full max-w-220" aria-labelledby="upload-title">
      <h1 id="upload-title" className="m-0 flex flex-wrap items-center gap-3 font-display text-title">
        <Marker>Tải tài liệu cho {name}</Marker>
      </h1>
      <div role="tablist" aria-label="Loại tài liệu" className="mt-6 flex flex-wrap gap-2 border-b border-line-strong">
        {TABS.map((t) => (
          <button
            key={t.role}
            type="button"
            role="tab"
            id={`tab-${t.role}`}
            aria-selected={tab === t.role}
            aria-controls={`panel-${t.role}`}
            onClick={() => setTab(t.role)}
            className={`-mb-px min-h-11 rounded-t-control border-b-2 px-4 text-read font-medium ${
              tab === t.role ? "border-ink bg-rose-100 font-semibold" : "border-transparent text-ink-soft"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {TABS.map((t) => (
        <div
          key={t.role}
          role="tabpanel"
          id={`panel-${t.role}`}
          aria-labelledby={`tab-${t.role}`}
          hidden={tab !== t.role}
        >
          <p className="mt-4 mb-0 max-w-[56ch] text-read text-ink-soft">{t.hint}</p>
          <Uploader subjectId={subjectId} hasMain={hasMain} fixedRole={t.role} />
        </div>
      ))}
      <p className="mt-6 mb-0">
        <a href="/subjects" className={AUTH_LINK}>
          Làm sau
        </a>
      </p>
    </Sheet>
  );
}
