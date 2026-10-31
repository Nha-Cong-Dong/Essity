"use client";

import { useRef, useState } from "react";

import { Marker, PencilNote } from "@/components/notebook";
import { Button } from "@/components/ui/button";
import {
  FIXTURES,
  PANEL_AT,
  type SyllabusFixture,
  type SyllabusState,
  SUBJECT,
} from "@/lib/fixtures/syllabus";
import { anyEdited, progress, sourceLabel, type SyllabusNode } from "@/lib/syllabus/tree";

import { SyllabusTree } from "./syllabus-tree";

// T7.5a (US-13 AC4, AC5, AC8, AC9; DESIGN §6.6; design-decisions.md): the Đề cương screen from typed
// fixtures, no API. Exactly one primary per state: "Vào buổi học", "Lưu" while a range is being
// edited (the tree owns it), "Tải giáo trình" with no main syllabus, "Thử lại" on error, none while
// loading or reading the contents.

export const COPY = {
  heading: "Đề cương",
  study: "Vào buổi học",
  upload: "Tải giáo trình",
  retry: "Thử lại",
  extracting: "Đang đọc mục lục…",
  empty: "Chưa có đề cương. Tải giáo trình chính để app dựng đề cương.",
  noOutline: "Chưa dựng được đề cương từ giáo trình này. Tải một giáo trình khác hoặc thử lại sau.",
  error: "Không tải được đề cương.",
  stillError: "Vẫn chưa tải được. Thử lại sau một chút.",
};

export const NOTICE = {
  chunk10: { long: "Chưa đọc được mục lục. Bạn có thể sửa trực tiếp.", short: "Chưa đọc được mục lục. Bạn có thể sửa trực tiếp." },
  scan: {
    long: "File này là ảnh chụp nên chưa đọc được chữ. Đề cương tạm chia theo khối 10 trang. Bạn có thể sửa trực tiếp.",
    short: "File này là ảnh chụp nên chưa đọc được chữ.",
  },
  flat: { long: "Mỗi slide là một mục. Chưa nhóm theo chương.", short: "Mỗi slide là một mục. Chưa nhóm theo chương." },
} as const;

export function Skeleton() {
  return (
    <div aria-hidden="true" className="mt-6 flex flex-col gap-3" data-skeleton>
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <div key={i} style={{ marginLeft: i % 3 === 0 ? 0 : 28 }} className="h-11 animate-pulse rounded-control bg-sunken motion-reduce:animate-none" />
      ))}
    </div>
  );
}

export function Totals({ nodes, unit }: { nodes: SyllabusNode[]; unit: SyllabusFixture["unit"] }) {
  const p = progress(nodes);
  const word = unit === "slide" ? "slide" : unit === "est_page" ? "trang ước tính" : "trang";
  const pct = p.pagesTotal === 0 ? 0 : Math.round((p.pagesDone / p.pagesTotal) * 100);
  return (
    <div className="mt-6">
      <p className="m-0 text-body" data-totals>
        đã học {p.done}/{p.total} mục · {p.pagesDone}/{p.pagesTotal} {word}
      </p>
      <div aria-hidden="true" className="mt-2 h-1 w-full overflow-hidden rounded-full bg-sunken">
        <div className="h-full rounded-full bg-correct" style={{ width: `${pct}%` }} />
      </div>
      {p.excluded > 0 && (
        <p className="m-0 mt-2 text-meta text-ink-soft">
          {p.excluded} mục không thi, không tính vào đây.
        </p>
      )}
    </div>
  );
}

export function SyllabusScreen({ state }: { state: SyllabusState }) {
  const fixture = (FIXTURES as Record<string, SyllabusFixture>)[state] ?? FIXTURES.ready;
  const [nodes, setNodes] = useState<SyllabusNode[]>(fixture.nodes);
  const [live, setLive] = useState("");
  const [editing, setEditing] = useState(PANEL_AT[state]?.mode === "edit");
  const alertRef = useRef<HTMLDivElement>(null);
  const subjectHref = `/subjects/${SUBJECT.id}`;

  const header = (
    <>
      <a href={subjectHref} className="inline-flex min-h-11 items-center text-meta text-ink-soft underline wrap-anywhere">
        ‹ {SUBJECT.name}
      </a>
      <div className="flex items-center justify-between gap-3">
        <h1 className="m-0 font-display text-title">
          <Marker>{COPY.heading}</Marker>
        </h1>
        {state !== "empty-no-main" && state !== "error" && state !== "loading" && state !== "extracting" && (
          <Button
            variant={editing ? "secondary" : "primary"}
            className="max-sm:px-4"
            render={<a href={`${subjectHref}/sessions/new`} />}
          >
            {COPY.study}
          </Button>
        )}
      </div>
    </>
  );

  const live_ = (
    <p role="status" className="sr-only" data-live>
      {live}
    </p>
  );

  if (state === "loading") {
    return (
      <div data-state={state}>
        {header}
        <p className="sr-only" role="status">Đang tải đề cương…</p>
        <Skeleton />
      </div>
    );
  }

  if (state === "error") {
    return (
      <div data-state={state}>
        {header}
        <div ref={alertRef} role="alert" tabIndex={-1} className="mt-6 rounded-sheet bg-sunken p-6 outline-none focus-visible:outline-2 focus-visible:outline-focus">
          <p className="m-0 text-body">{COPY.error}</p>
          <div className="mt-4">
            <Button
              onClick={() => {
                setLive(COPY.stillError);
                alertRef.current?.focus();
              }}
            >
              {COPY.retry}
            </Button>
          </div>
        </div>
        {live_}
      </div>
    );
  }

  if (state === "empty-no-main") {
    return (
      <div data-state={state}>
        {header}
        <div className="mt-6 rounded-sheet bg-rose-50 p-6">
          <p className="m-0 text-body">{COPY.empty}</p>
          <div className="mt-4">
            <Button render={<a href={`${subjectHref}/upload`} />}>{COPY.upload}</Button>
          </div>
        </div>
      </div>
    );
  }

  if (state === "extracting") {
    return (
      <div data-state={state}>
        {header}
        <p role="status" aria-busy="true" className="m-0 mt-6 text-body text-ink-soft">
          {COPY.extracting}
        </p>
        <Skeleton />
      </div>
    );
  }

  const note = fixture.notice ? NOTICE[fixture.notice] : null;
  return (
    <div data-state={state}>
      {header}
      <p className="m-0 mt-1 flex flex-wrap items-baseline gap-x-3 text-read wrap-anywhere" data-main>
        <span data-user>{fixture.mainName}</span>
        <PencilNote>{sourceLabel(fixture.source, anyEdited(nodes))}</PencilNote>
      </p>
      {note && (
        <div className="mt-4 rounded-sheet bg-sunken p-4 text-body" data-notice={fixture.notice}>
          <p className="m-0">
            <span className="sm:hidden">{note.short}</span>
            <span className="max-sm:hidden">{note.long}</span>
          </p>
        </div>
      )}
      <Totals nodes={nodes} unit={fixture.unit} />
      <div className="mt-4">
        <SyllabusTree
          label={`Đề cương ${fixture.mainName}`}
          nodes={nodes}
          unit={fixture.unit}
          total={fixture.total}
          onNodes={setNodes}
          say={setLive}
          onEditing={setEditing}
          initialPanel={PANEL_AT[state] ? { ...PANEL_AT[state]!, focus: false } : null}
        />
      </div>
      {live_}
    </div>
  );
}
