"use client";

import { NX_CAM, NxChip } from "@/components/ui/nx-list";
import { useEffect, useRef, useState } from "react";

import { Pen } from "@/components/practice/practice-extras";
import { PracticeAnswer } from "@/components/practice/practice-answer";
import { CoverageBar } from "@/components/stats/stat-tile";
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

/** Ready first (the latest unlocked first, V20), then waiting; the list's own order is kept otherwise. */
function ordered(rows: QuestionRow[]): QuestionRow[] {
  const rank = { ready: 0, waiting: 1, unlinked: 2 } as const;
  const at = (q: QuestionRow) => (q.unlocked_at ? Date.parse(q.unlocked_at) : 0);
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => rank[a.row.status] - rank[b.row.status] || at(b.row) - at(a.row) || a.index - b.index)
    .map(({ row }) => row);
}

function unlockedOn(iso: string): string {
  const d = new Date(iso);
  return `${d.getDate()}/${d.getMonth() + 1}`;
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

/** The kind name for the chip: a short readable name, never a raw key (no spaces and long = a key). */
export function kindChip(name: string): string | null {
  const t = name.trim();
  if (t === "") return null;
  return !/\s/.test(t) && t.length > 24 ? null : t;
}

const TILE = "min-w-0 rounded-tile bg-hong-tint p-4 min-[901px]:p-6";

function Row({
  q,
  subjectId,
  primary,
  pick,
  why,
  removed,
  onDo,
  onRemove,
  onUndo,
}: {
  q: QuestionRow;
  subjectId: string;
  primary: boolean;
  /** The one question the screen suggests: a cam row, with its reason. */
  pick: boolean;
  why: string;
  removed: boolean;
  onDo: () => void;
  onRemove: () => void;
  onUndo: () => void;
}) {
  if (removed) {
    return (
      <li
        data-removed={q.id}
        className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-row bg-bg px-4 py-3"
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
    <li
      data-question={q.id}
      className={`flex flex-col items-start gap-2 rounded-row bg-bg px-4 py-3.5 ${pick ? NX_CAM.pick : ""}`}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {kindChip(q.type_name) !== null && (
          <NxChip className="h-auto min-h-7 max-w-full py-1">
            <span data-user className="wrap-anywhere">
              {kindChip(q.type_name)}
            </span>
          </NxChip>
        )}
        <span className="text-meta text-ink-soft">{q.origin === "bank" ? "Câu gốc" : "Câu sinh thêm"}</span>
        {q.number !== null && <span className="text-meta text-ink-soft">Câu {q.number}</span>}
        {q.status === "waiting" ? (
          <a href={`/subjects/${subjectId}/syllabus`} className="text-meta inline-flex items-center justify-center min-h-11 rounded-full bg-sheet px-4 font-medium text-ink no-underline inset-ring-1 inset-ring-line-strong hover:bg-sunken">
            {q.line}
          </a>
        ) : q.status === "unlinked" ? (
          <span className="text-meta text-ink-soft">Chưa gắn phần</span>
        ) : (
          <span className="text-meta text-ink-soft">{q.line}</span>
        )}
        {q.unlocked_at && <span className="text-meta text-ink-soft">Mở khóa {unlockedOn(q.unlocked_at)}</span>}
      </div>
      <p id={`sum-${q.id}`} data-user className="m-0 line-clamp-3 wrap-anywhere">
        {q.prompt}
      </p>
      {pick && (
        <p data-why className={`m-0 text-meta ${NX_CAM.text}`}>
          <span aria-hidden="true">→ </span>
          {why}
        </p>
      )}
      {q.answer_source === "ai" && <Pen>đáp án do AI soạn</Pen>}
      <div className="flex w-full flex-col items-stretch gap-1 sm:flex-row sm:flex-wrap sm:items-center">
        {q.status === "ready" && (
          <Button variant={primary ? "primary" : "secondary"} data-focus={`do-${q.id}`} aria-describedby={`sum-${q.id}`} className={FULL} onClick={onDo}>
            Làm câu này
          </Button>
        )}
        {/* One main button per card; removing is a small ghost pill kept apart (ux-critic 05/11). */}
        <Button variant="quiet" aria-describedby={`sum-${q.id}`} className="mt-3 self-start sm:mt-0 sm:ml-2" onClick={onRemove}>
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
  const unlockedRows = ordered(list.questions.filter((q) => q.status === "ready"));
  const waitingRows = list.questions.filter((q) => q.status === "waiting");
  const firstReady = unlockedRows.find((q) => !removed.has(q.id))?.id ?? null;
  const dueNow = list.questions.filter((q) => q.due === true && !removed.has(q.id));
  const readyCount = live.filter((q) => q.status === "ready").length;

  const pickId = dueNow[0]?.id ?? firstReady;
  const dueButton = dueNow.length > 0; // then that button is the screen's primary
  const rows = (items: QuestionRow[], primaryId: string | null) => (
    <ul className="m-0 mt-3 flex list-none flex-col gap-1.5 p-0">
      {items.map((q) => (
        <Row
          key={q.id}
          q={q}
          subjectId={subjectId}
          primary={!dueButton && q.id === primaryId}
          pick={q.id === pickId}
          why={dueNow.some((d) => d.id === q.id) ? "Gợi ý: đến hạn luyện hôm nay" : "Gợi ý: câu mở khóa mới nhất"}
          removed={removed.has(q.id)}
          onDo={() => setDoing(q.id)}
          onRemove={() => void remove(q.id)}
          onUndo={() => void undo(q.id)}
        />
      ))}
    </ul>
  );

  return (
    <div ref={root} className="w-full max-w-240">
      <a href={`/subjects/${subjectId}`} className="text-meta wrap-anywhere inline-flex items-center justify-center min-h-11 rounded-full bg-sheet px-4 font-medium text-ink no-underline inset-ring-1 inset-ring-line-strong hover:bg-sunken">
        ← {subjectName}
      </a>
      <div className="mt-3 flex flex-wrap items-end justify-between gap-x-8 gap-y-3" data-practice-head>
        <div className="min-w-0 basis-80 flex-1">
          <h1 className="m-0 font-display text-title">
            <span className="hl-word">Luyện tập</span>
          </h1>
          <p className="m-0 mt-1 text-read text-ink-soft wrap-anywhere" data-practice-sub>
            {list.total === 0
              ? subjectName
              : `${readyCount} câu sẵn sàng${types.length > 0 ? ` · ${types.length} dạng` : ""} · `}
            {list.total === 0 ? null : <span data-user>{subjectName}</span>}
          </p>
        </div>
      </div>
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
        <div className="mt-6 grid gap-6 min-[1000px]:grid-cols-12 min-[1000px]:items-start">
          {/* UI-A/B: the answer of the screen (unlocked / total) and the one action sit in a right column. */}
          <aside
            className="flex flex-col gap-4 rounded-tile bg-hong-tint p-5 min-[1000px]:sticky min-[1000px]:top-6 min-[1000px]:col-start-9 min-[1000px]:col-end-13 min-[1000px]:row-start-1 min-[1000px]:p-6"
            data-practice-today
          >
            <div data-progress>
              <p className="m-0 flex items-baseline gap-2">
                <span className="font-display text-display tabular-nums">{readyCount}</span>{" "}
                <span className="text-lead font-semibold">/ {live.length} câu</span>
              </p>
              <p data-summary className="m-0 mt-1 text-read">
                Đã mở khóa {readyCount}/{live.length} câu
              </p>
              <div className="mt-3">
                <CoverageBar percent={live.length === 0 ? 0 : (readyCount / live.length) * 100} />
              </div>
            </div>
            {list.due_today !== undefined && (
              <div data-due className="flex flex-wrap items-center gap-x-4 gap-y-2">
                <p className="m-0 text-read">
                  {dueNow.length > 0 ? `Hôm nay cần luyện ${dueNow.length} câu.` : "Hôm nay không có câu nào cần luyện."}
                </p>
              </div>
            )}
            {dueNow.length > 0 && (
              <Button className={FULL} onClick={() => setDoing(dueNow[0].id)}>
                Vào luyện tập ngay
              </Button>
            )}
          </aside>
          {firstReady === null && (
            <>
              <p className="m-0 mt-3">Chưa có câu hỏi nào sẵn sàng, hãy kết nối thêm kiến thức để mở khóa câu hỏi nhé!</p>
              <Button render={<a href={`/subjects/${subjectId}/sessions/new`} />} nativeButton={false} className={`mt-4 ${FULL}`}>
                Vào buổi học
              </Button>
            </>
          )}
          <section aria-labelledby="practised" className={`${TILE} min-[1000px]:col-span-8 min-[1000px]:col-start-1 min-[1000px]:row-start-1`} data-practised data-nx>
            <div className="flex items-baseline justify-between gap-3">
              <h2 id="practised" className="m-0 font-display text-lead max-[640px]:text-body max-[640px]:font-semibold">
                Câu đã luyện tập
              </h2>
            </div>
            <p className="m-0 mt-1 text-meta text-ink-soft">Sắp theo ngày mở khóa, mới nhất trước.</p>
            {unlockedRows.length === 0 ? (
              <p className="m-0 mt-3 text-ink-soft">Chưa có câu nào mở khóa.</p>
            ) : (
              rows(unlockedRows, firstReady)
            )}
            {groups.some((g) => g.type !== null) && (
              <details className="mt-4" data-types>
                <summary className="flex min-h-11 cursor-pointer items-center text-meta rounded-full bg-sheet px-4 font-medium text-ink no-underline inset-ring-1 inset-ring-line-strong hover:bg-sunken">Theo dạng câu</summary>
                {groups
                  .filter((g) => g.type !== null)
                  .map((g) => (
                    <div key={g.key} className="mt-2">
                      <p className="m-0 text-meta font-semibold wrap-anywhere">
                        <span data-user>{g.name}</span>
                      </p>
                      <p data-mastery className="m-0 text-meta text-ink-soft">
                        {g.type?.mastery_line}
                      </p>
                      <p data-sensitivity className="m-0 text-meta text-ink-soft">
                        {g.type?.sensitivity_line}
                      </p>
                    </div>
                  ))}
              </details>
            )}
          </section>
          {waitingRows.length > 0 && (
            <section aria-labelledby="waiting" className={`${TILE} min-[1000px]:col-span-8 min-[1000px]:col-start-1`} data-nx>
              <h2 id="waiting" className="m-0 text-read font-semibold">
                Chờ mở khóa
              </h2>
              {rows(waitingRows, null)}
            </section>
          )}
          {unlinked.length > 0 && (
            <section aria-labelledby="unlinked" className={`mt-8 ${TILE}`} data-nx>
              <h2 id="unlinked" className="m-0 text-read font-semibold">
                Chưa gắn phần
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
