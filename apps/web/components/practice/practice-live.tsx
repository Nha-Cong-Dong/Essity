"use client";

import { useEffect, useRef, useState } from "react";

import { Pen } from "@/components/practice/practice-extras";
import { PracticeAnswer } from "@/components/practice/practice-answer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { go } from "@/lib/navigate";
import { type PracticeApi, practiceApi, type PracticeType } from "@/lib/practice-client";
import type { QuestionListOut, QuestionRow } from "@/lib/question-list-types";

// T8.7 (US-16 AC1-AC3, AC8; DESIGN §6.12, D26-D27): the Luyện tập screen on the real API. The
// types come from /v1/subjects/{id}/practice-types (mastery and sensitivity already worded by the
// backend: "chưa đủ dữ liệu" under 3 answers, neutral words for time), the questions from the
// bank list (T8.2). One primary button: the first ready row. "Làm câu này" answers in place with
// PracticeAnswer; "Gỡ khỏi luyện tập" is one tap, no dialog ("Hoàn tác" calls restore, T8.7b).

const FULL = "max-sm:w-full";
const OTHER_TYPE = "Chưa có dạng";

type Group = { key: string; name: string; type: PracticeType | null; rows: QuestionRow[] };

/** Ready first, then waiting; the list's own (newest-first) order is kept inside each. */
function ordered(rows: QuestionRow[]): QuestionRow[] {
  const rank = { ready: 0, waiting: 1, unlinked: 2 } as const;
  return rows.map((row, index) => ({ row, index })).sort((a, b) => rank[a.row.status] - rank[b.row.status] || a.index - b.index).map(({ row }) => row);
}

export function groupQuestions(list: QuestionListOut, types: PracticeType[]): { groups: Group[]; unlinked: QuestionRow[] } {
  const linked = list.questions.filter((q) => q.status !== "unlinked");
  const byName = new Map<string, QuestionRow[]>();
  for (const q of linked) byName.set(q.type_name, [...(byName.get(q.type_name) ?? []), q]);
  const groups: Group[] = types
    .filter((t) => byName.has(t.name))
    .map((t) => ({ key: t.type_id, name: t.name, type: t, rows: ordered(byName.get(t.name) ?? []) }));
  const known = new Set(types.map((t) => t.name));
  for (const [name, rows] of byName) {
    if (!known.has(name)) groups.push({ key: `name-${name}`, name: name || OTHER_TYPE, type: null, rows: ordered(rows) });
  }
  return { groups, unlinked: list.questions.filter((q) => q.status === "unlinked") };
}

function Row({
  q,
  subjectId,
  primary,
  removed,
  onDo,
  onRemove,
  onUndo,
}: {
  q: QuestionRow;
  subjectId: string;
  primary: boolean;
  removed: boolean;
  onDo: () => void;
  onRemove: () => void;
  onUndo: () => void;
}) {
  if (removed) {
    return (
      <li
        data-removed={q.id}
        className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line bg-sunken px-3 py-3 first:border-t-0"
      >
        <span tabIndex={-1} data-focus={`removed-${q.id}`} className="outline-none">
          Đã gỡ khỏi luyện tập.
        </span>
        <Button variant="quiet" aria-describedby={`sum-${q.id}`} onClick={onUndo}>
          Hoàn tác
        </Button>
        <span id={`sum-${q.id}`} data-user className="sr-only">
          {q.prompt}
        </span>
      </li>
    );
  }
  return (
    <li data-question={q.id} className="flex flex-col gap-2 border-t border-line py-4 first:border-t-0">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Badge variant="level">{q.origin === "bank" ? "Câu gốc" : "Câu sinh thêm"}</Badge>
        {q.status === "ready" && <span className="text-meta">{q.line}</span>}
        {q.status === "waiting" && (
          <a href={`/subjects/${subjectId}/syllabus`} className="text-meta underline">
            {q.line}
          </a>
        )}
        {q.status === "unlinked" && <span className="text-meta text-ink-soft">Chưa gắn mục</span>}
        {q.number !== null && <span className="text-meta text-ink-soft">Câu {q.number}</span>}
      </div>
      <p id={`sum-${q.id}`} data-user className="m-0 line-clamp-3 wrap-anywhere">
        {q.prompt}
      </p>
      {q.answer_source === "ai" && <Pen>đáp án do AI soạn</Pen>}
      <div className="flex flex-col items-stretch gap-1 sm:flex-row sm:flex-wrap sm:items-center">
        {q.status === "ready" && (
          <Button variant={primary ? "primary" : "secondary"} data-focus={`do-${q.id}`} aria-describedby={`sum-${q.id}`} className={FULL} onClick={onDo}>
            Làm câu này
          </Button>
        )}
        <Button variant="quiet" aria-describedby={`sum-${q.id}`} onClick={onRemove}>
          Gỡ khỏi luyện tập
        </Button>
      </div>
    </li>
  );
}

export function PracticeLive({
  subjectId,
  subjectName,
  list,
  types,
  listPath = `/subjects/${subjectId}/practice`,
  api = practiceApi,
}: {
  subjectId: string;
  subjectName: string;
  list: QuestionListOut;
  types: PracticeType[];
  /** Where "Câu tiếp" goes: the list again, read afresh (mastery and statuses have moved). */
  listPath?: string;
  api?: PracticeApi;
}) {
  const [doing, setDoing] = useState<string | null>(null);
  const [removed, setRemoved] = useState<Set<string>>(new Set());
  const [failed, setFailed] = useState(false);
  const [focus, setFocus] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (focus) root.current?.querySelector<HTMLElement>(`[data-focus="${focus}"]`)?.focus();
  }, [focus, removed]);

  if (doing !== null) {
    return <PracticeAnswer questionId={doing} api={api} onNext={() => go(listPath)} />;
  }

  async function remove(id: string) {
    setFailed(false);
    const reply = await api.remove(id);
    if (!reply.ok) {
      setFailed(true);
      return;
    }
    setRemoved((was) => new Set(was).add(id));
    setFocus(`removed-${id}`);
  }

  const { groups, unlinked } = groupQuestions(list, types);
  async function undo(id: string) {
    setFailed(false);
    const reply = await api.restore(id);
    if (!reply.ok) {
      setFailed(true);
      return;
    }
    setRemoved((was) => {
      const next = new Set(was);
      next.delete(id);
      return next;
    });
    setFocus(`do-${id}`);
  }

  const live = list.questions.filter((q) => !removed.has(q.id));
  const firstReady = groups.flatMap((g) => g.rows).find((q) => q.status === "ready" && !removed.has(q.id))?.id ?? null;

  const rows = (items: QuestionRow[], primaryId: string | null) => (
    <ul className="m-0 mt-3 flex list-none flex-col p-0">
      {items.map((q) => (
        <Row
          key={q.id}
          q={q}
          subjectId={subjectId}
          primary={q.id === primaryId}
          removed={removed.has(q.id)}
          onDo={() => setDoing(q.id)}
          onRemove={() => void remove(q.id)}
          onUndo={() => void undo(q.id)}
        />
      ))}
    </ul>
  );

  return (
    <div ref={root} className="mx-auto w-full max-w-180">
      <a href={`/subjects/${subjectId}`} className="text-meta text-ink-soft underline wrap-anywhere">
        ← {subjectName}
      </a>
      <h1 className="m-0 mt-3 font-display text-title">Luyện tập</h1>
      <p className="m-0 mt-1 text-read text-ink-soft wrap-anywhere">{subjectName}</p>
      <p role="status" className="sr-only">
        {removed.size > 0 ? "Đã gỡ khỏi luyện tập." : ""}
      </p>
      {failed && (
        <p role="alert" className="m-0 mt-4 text-meta">
          Chưa gỡ được. Bạn bấm lại nhé.
        </p>
      )}
      {list.total === 0 ? (
        <div data-empty className="mt-6">
          <p className="m-0">
            Chưa có bộ câu hỏi. Tải đề cương ôn, đề năm trước hoặc bộ câu hỏi thầy cô cho để luyện đúng dạng đề thi.
          </p>
          <Button render={<a href={`/subjects/${subjectId}/documents`} />} nativeButton={false} className={`mt-4 ${FULL}`}>
            Tải bộ câu hỏi
          </Button>
        </div>
      ) : (
        <div className="mt-6">
          <p data-summary className="m-0 text-read">
            {live.length} câu · {live.filter((q) => q.status === "ready").length} sẵn sàng
          </p>
          {firstReady === null && (
            <>
              <p className="m-0 mt-3">Chưa có câu sẵn sàng. Câu sẽ sẵn sàng khi bạn học xong mục của nó.</p>
              <Button render={<a href={`/subjects/${subjectId}/sessions/new`} />} nativeButton={false} className={`mt-4 ${FULL}`}>
                Vào buổi học
              </Button>
            </>
          )}
          {groups.map((g) => (
            <section key={g.key} aria-labelledby={`g-${g.key}`} className="mt-8">
              <h2 id={`g-${g.key}`} className="m-0 text-read font-semibold wrap-anywhere">
                <span data-user>{g.name}</span>
              </h2>
              {g.type && (
                <>
                  <p data-mastery className="m-0 mt-1 text-meta text-ink-soft">
                    {g.type.mastery_line}
                  </p>
                  <p data-sensitivity className="m-0 text-meta text-ink-soft">
                    {g.type.sensitivity_line}
                  </p>
                </>
              )}
              {rows(g.rows, firstReady)}
            </section>
          ))}
          {unlinked.length > 0 && (
            <section aria-labelledby="unlinked" className="mt-8">
              <h2 id="unlinked" className="m-0 text-read font-semibold">
                Chưa gắn mục
              </h2>
              <p className="m-0 mt-1 text-meta text-ink-soft">Sửa bằng thanh lệnh.</p>
              {rows(unlinked, null)}
            </section>
          )}
        </div>
      )}
    </div>
  );
}
