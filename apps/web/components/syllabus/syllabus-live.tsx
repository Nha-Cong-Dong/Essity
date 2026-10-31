"use client";

import { useEffect, useRef, useState } from "react";

import { Marker, PencilNote } from "@/components/notebook";
import { Button } from "@/components/ui/button";
import {
  diffChanges,
  type OutlineOut,
  outlineView,
  patchSection,
  readOutline,
} from "@/lib/syllabus/api";
import { anyEdited, sourceLabel, type SyllabusNode } from "@/lib/syllabus/tree";

import { COPY, NOTICE, Skeleton, Totals } from "./syllabus-screen";
import { SyllabusTree } from "./syllabus-tree";

// T7.5 (US-13 AC1, AC4-AC6, AC9; US-01 AC5; DESIGN §6.6): the Đề cương screen on the real API. The
// look is T7.5a's (syllabus-screen.tsx, syllabus-tree.tsx); this file only loads, polls while the
// textbook is being read, and sends each action as PATCHes. An action shows at once and is undone
// with a visible message when core-api refuses it; core-api's answer is the truth after each one.

const POLL_MS = 4000;

const REFUSED: Record<string, string> = {
  invalid_range: "Khoảng trang này không hợp lệ.",
  outside_document: "Khoảng này vượt quá số trang của giáo trình.",
  outside_parent: "Khoảng này nằm ngoài mục cha.",
  children_outside: "Khoảng này không phủ hết các mục con.",
  offline: "Chưa lưu được vì mất kết nối. Thử lại.",
};
const NOT_SAVED = "Chưa lưu được. Thử lại.";

export function SyllabusLive({
  subjectId,
  subjectName,
  initial,
}: {
  subjectId: string;
  subjectName: string;
  initial: OutlineOut;
}) {
  const [outline, setOutline] = useState(initial);
  // The learner's action shown before core-api answers; null = what core-api last said.
  const [local, setLocal] = useState<SyllabusNode[] | null>(null);
  const [live, setLive] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const [, setEditing] = useState(false);
  const queue = useRef<Promise<void>>(Promise.resolve());
  const view = outlineView(outline);
  const nodes = local ?? (view.kind === "ready" ? view.nodes : []);
  const nodesRef = useRef(nodes);
  useEffect(() => {
    nodesRef.current = nodes;
  });
  const waiting = view.kind === "none" && view.reason === "not_indexed";
  const subjectHref = `/subjects/${subjectId}`;

  // While the textbook is read, ask again; it stops when the outline (or a final state) arrives.
  useEffect(() => {
    if (!waiting) return;
    const timer = setInterval(async () => {
      const next = await readOutline(subjectId);
      if (next.ok) setOutline(next.data);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [waiting, subjectId]);

  function change(next: SyllabusNode[]) {
    const changes = diffChanges(nodesRef.current, next);
    if (changes.length === 0) return;
    setFailure(null);
    setLocal(next);
    queue.current = queue.current.then(async () => {
      let last: OutlineOut | null = null;
      for (const { id, body } of changes) {
        const sent = await patchSection(id, body);
        if (!sent.ok) {
          const text = REFUSED[sent.code] ?? NOT_SAVED;
          setFailure(text);
          setLive(text);
          // Whatever was saved before the refusal is in `last`; ask again for the rest.
          const fresh = last ? { ok: true as const, data: last } : await readOutline(subjectId);
          if (fresh.ok) setOutline(fresh.data);
          setLocal(null);
          return;
        }
        last = sent.data;
      }
      if (last) setOutline(last);
      setLocal(null);
    });
  }

  const header = (
    <>
      <a href={subjectHref} className="inline-flex min-h-11 items-center text-meta text-ink-soft underline wrap-anywhere">
        ‹ {subjectName}
      </a>
      <div className="flex items-center justify-between gap-3">
        <h1 className="m-0 font-display text-title">
          <Marker>{COPY.heading}</Marker>
        </h1>
        {view.kind === "ready" && (
          <Button className="max-sm:px-4" render={<a href={`${subjectHref}/sessions/new`} />}>
            {COPY.study}
          </Button>
        )}
      </div>
    </>
  );

  if (view.kind === "none") {
    if (waiting) {
      return (
        <div data-state="extracting">
          {header}
          <p role="status" aria-busy="true" className="m-0 mt-6 text-body text-ink-soft">
            {COPY.extracting}
          </p>
          <Skeleton />
        </div>
      );
    }
    return (
      <div data-state={view.reason === "no_textbook" ? "empty-no-main" : "no-outline"}>
        {header}
        <div className="mt-6 rounded-sheet bg-rose-50 p-6">
          <p className="m-0 text-body">{view.reason === "no_textbook" ? COPY.empty : COPY.noOutline}</p>
          <div className="mt-4">
            <Button render={<a href={`${subjectHref}/upload`} />}>{COPY.upload}</Button>
          </div>
        </div>
      </div>
    );
  }

  const note = view.temporary ? NOTICE.chunk10 : null;
  return (
    <div data-state={view.temporary ? "provisional" : "ready"}>
      {header}
      <p className="m-0 mt-1 flex flex-wrap items-baseline gap-x-3 text-read wrap-anywhere" data-main>
        <span data-user>{view.name}</span>
        <PencilNote>{sourceLabel(view.source, anyEdited(nodes))}</PencilNote>
      </p>
      {note && (
        <div className="mt-4 rounded-sheet bg-sunken p-4 text-body" data-notice="chunk10">
          <p className="m-0">
            <span className="sm:hidden">{note.short}</span>
            <span className="max-sm:hidden">{note.long}</span>
          </p>
        </div>
      )}
      <Totals nodes={nodes} unit={view.unit} />
      {failure && (
        <p role="alert" className="m-0 mt-4 text-body" data-save-failure>
          {failure}
        </p>
      )}
      <div className="mt-4">
        <SyllabusTree
          label={`Đề cương ${view.name}`}
          nodes={nodes}
          unit={view.unit}
          total={view.total}
          onNodes={change}
          say={setLive}
          onEditing={setEditing}
        />
      </div>
      <p role="status" className="sr-only" data-live>
        {live}
      </p>
    </div>
  );
}
