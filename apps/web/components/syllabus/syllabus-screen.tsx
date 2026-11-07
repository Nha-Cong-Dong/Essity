"use client";

import { type ReactNode, useRef, useState } from "react";

import { EmptyState } from "@/components/empty-state";
import { PencilNote } from "@/components/notebook";
import { Block, BackLink } from "@/components/screen-kit";
import { Button } from "@/components/ui/button";
import {
  FIXTURES,
  PANEL_AT,
  type SyllabusFixture,
  type SyllabusState,
  SUBJECT,
} from "@/lib/fixtures/syllabus";
import { anyEdited, prettyDocName, progress, sourceNote, type SyllabusNode } from "@/lib/syllabus/tree";

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
  flat: { long: "Mỗi slide là một phần. Chưa nhóm theo chương.", short: "Mỗi slide là một phần. Chưa nhóm theo chương." },
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

/** The tile of the landing's "Học gì tiếp" list: the subject on the left, "Gợi ý, bạn chọn" on the right, the tree below. */
export function SyllabusTile({ name, children }: { name: string; children: ReactNode }) {
  return (
    <Block as="section" tier="sheet" data-nx className="p-4 max-sm:p-3 min-[901px]:p-6">
      <div className="flex items-baseline justify-between gap-3 pb-3.5">
        <h2 className="m-0 min-w-0 font-display text-lead wrap-anywhere max-[640px]:text-body max-[640px]:font-semibold">{name}</h2>
        <span className="shrink-0 text-meta italic text-ink-soft">Gợi ý, bạn chọn</span>
      </div>
      {children}
    </Block>
  );
}

export function Totals({ nodes, unit }: { nodes: SyllabusNode[]; unit: SyllabusFixture["unit"] }) {
  const p = progress(nodes);
  const word = unit === "slide" ? "slide" : unit === "est_page" ? "trang ước tính" : "trang";
  const pct = p.pagesTotal === 0 ? 0 : Math.round((p.pagesDone / p.pagesTotal) * 100);
  return (
    <Block tier="field" className="mt-6 p-5 min-[901px]:p-6" data-totals-block>
      <p className="m-0 text-lead" data-totals>
        đã học {p.done}/{p.total} phần · {p.pagesDone}/{p.pagesTotal} {word}
      </p>
      <div aria-hidden="true" className="mt-3 h-2 w-full overflow-hidden rounded-full bg-on-plum/20">
        <div className="h-full rounded-full bg-on-plum-action" style={{ width: `${pct}%` }} />
      </div>
      {p.excluded > 0 && (
        <p className="m-0 mt-2 text-meta text-on-plum-soft">
          {p.excluded} phần không thi, không tính vào đây.
        </p>
      )}
    </Block>
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
      <BackLink href={subjectHref}>{SUBJECT.name}</BackLink>
      <div className="flex items-center justify-between gap-3">
        <h1 className="m-0 font-display text-title">
          {COPY.heading}
        </h1>
        {state !== "empty-no-main" && state !== "error" && state !== "loading" && state !== "extracting" && (
          <Button
            variant={editing ? "secondary" : "primary"}
            className="max-sm:px-4"
            render={<a href={`${subjectHref}/sessions/new`} />}
            nativeButton={false}
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
        <div ref={alertRef} role="alert" tabIndex={-1} className="mt-6 rounded-tile outline-none focus-visible:outline-2 focus-visible:outline-focus">
          <Block tier="sheet">
            <EmptyState
              mascot="nghi"
              title={COPY.error}
              action={
                <Button
                  onClick={() => {
                    setLive(COPY.stillError);
                    alertRef.current?.focus();
                  }}
                >
                  {COPY.retry}
                </Button>
              }
            />
          </Block>
        </div>
        {live_}
      </div>
    );
  }

  if (state === "empty-no-main") {
    return (
      <div data-state={state}>
        {header}
        <Block tier="sheet" className="mt-6">
          <EmptyState
            mascot="rong"
            title={COPY.empty}
            action={<Button render={<a href={`${subjectHref}/upload`} />} nativeButton={false}>{COPY.upload}</Button>}
          />
        </Block>
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
        <span data-user>{prettyDocName(fixture.mainName)}</span>
        {sourceNote(fixture.source, anyEdited(nodes)) && <PencilNote>{sourceNote(fixture.source, anyEdited(nodes))}</PencilNote>}
      </p>
      {note && (
        <Block tier="tint" className="mt-4 p-4 text-body min-[901px]:p-4" data-notice={fixture.notice}>
          <p className="m-0">
            <span className="sm:hidden">{note.short}</span>
            <span className="max-sm:hidden">{note.long}</span>
          </p>
        </Block>
      )}
      <Totals nodes={nodes} unit={fixture.unit} />
      <div className="mt-4">
        <SyllabusTile name={SUBJECT.name}>
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
        </SyllabusTile>
      </div>
      {live_}
    </div>
  );
}
