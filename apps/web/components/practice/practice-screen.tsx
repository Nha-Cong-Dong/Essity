"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";

import { Marker } from "@/components/notebook";
import { GradeResult } from "@/components/review/grade-result";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet } from "@/components/ui/sheet";
import {
  CANDIDATES,
  type Candidate,
  GROUPS,
  IMPORTED_FILE,
  IMPORTED_NOTE,
  type PracticeGroup,
  type PracticeState,
  RESULT,
  RESULT_EXTRAS,
  SECTIONS,
  type StudiedSection,
  SUBJECT,
  UNLINKED,
  WAITING_ONLY,
} from "@/lib/fixtures/practice";
import { masteryText, orderedRows, type PracticeQuestion, summaryLine, timingLine } from "@/lib/practice";

// T8.7a (US-14, US-16, US-17; DESIGN §6.12, design-decisions.md in .work/T8.7a): the Luyện tập
// screen from typed fixtures, no API. Exactly one primary button per state (none while loading or
// importing). The first ready row, or the first undecided candidate, owns it. A removed row turns
// into "Đã gỡ khỏi luyện tập. Hoàn tác" in place: one tap, no dialog, no timer.

const FULL = "max-sm:w-full";
const COPY = {
  heading: "Luyện tập",
  doNow: "Làm câu này",
  addMore: "Thêm câu như thế này",
  remove: "Gỡ khỏi luyện tập",
  keep: "Đưa vào luyện tập",
  discard: "Không giữ",
  upload: "Tải bộ câu hỏi",
  generate: "Sinh câu luyện tập cho mục này",
  retry: "Thử lại",
  study: "Vào buổi học",
  view: "Xem câu hỏi",
  undo: "Hoàn tác",
  next: "Câu tiếp",
};

type Owner = "candidate" | "upload" | "session" | "retry" | "view" | "row" | "none";
type Decisions = Record<string, "kept" | "dropped">;

function ownerFor(state: PracticeState, candidateOpen: boolean): Owner {
  if (candidateOpen) return "candidate";
  switch (state) {
    case "no-bank":
      return "upload";
    case "empty-ready":
      return "session";
    case "error":
      return "retry";
    case "imported":
      return "view";
    case "loading":
    case "importing":
    case "result":
      return "none";
    default:
      return "row";
  }
}

function Skeleton() {
  return (
    <div aria-hidden="true" className="mt-6 flex flex-col gap-3">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-14 animate-pulse rounded-control bg-sunken" />
      ))}
    </div>
  );
}

function Pen({ children }: { children: ReactNode }) {
  return <span className="font-hand text-body text-pencil">{children}</span>;
}

function CandidateReview({
  title,
  items,
  decided,
  primaryOn,
  onClose,
  onDecide,
}: {
  title: string;
  items: Candidate[];
  decided: Decisions;
  primaryOn: boolean;
  onClose: () => void;
  onDecide: (id: string, how: "kept" | "dropped") => void;
}) {
  const firstOpen = items.find((c) => !decided[c.id])?.id;
  return (
    <Sheet variant="sunken" className="mt-4" data-candidates>
      <h3 className="m-0 text-read font-semibold wrap-anywhere">
        Câu sinh thêm cho: <span data-user>{title}</span>
      </h3>
      {items.length === 0 ? (
        <p className="m-0 mt-3">Chưa có câu sinh thêm nào đủ tốt. Thử lại sau khi học thêm thẻ.</p>
      ) : (
        <>
          <p className="m-0 mt-1 text-meta text-ink-soft">Chỉ dùng thẻ bạn đã học.</p>
          <ul className="m-0 mt-4 flex list-none flex-col gap-4 p-0">
            {items.map((c) => (
              <li key={c.id} className="flex flex-col gap-2 rounded-control bg-sheet p-4">
                <p id={`cand-${c.id}`} data-user className="m-0 wrap-anywhere">
                  {c.text}
                </p>
                <p className="m-0 text-meta text-ink-soft wrap-anywhere">
                  <span data-user>{c.kind}</span> ·{" "}
                  <a href="#" data-user className="underline">
                    {c.cardLabel}
                  </a>
                </p>
                <Pen>đáp án do AI soạn</Pen>
                {decided[c.id] ? (
                  <p className="m-0 text-meta">
                    {decided[c.id] === "kept" ? "Đã đưa vào luyện tập." : "Sẽ không nhắc lại câu này."}
                  </p>
                ) : (
                  <div className="flex flex-col items-stretch gap-1 sm:flex-row sm:items-center">
                    <Button
                      variant={primaryOn && firstOpen === c.id ? "primary" : "secondary"}
                      className={FULL}
                      aria-describedby={`cand-${c.id}`}
                      onClick={() => onDecide(c.id, "kept")}
                    >
                      {COPY.keep}
                    </Button>
                    <Button variant="quiet" aria-describedby={`cand-${c.id}`} onClick={() => onDecide(c.id, "dropped")}>
                      {COPY.discard}
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
          {firstOpen === undefined && <p className="m-0 mt-4">Đã xem hết các câu ứng viên.</p>}
        </>
      )}
      <Button variant="quiet" className="mt-3" onClick={onClose}>
        Đóng
      </Button>
    </Sheet>
  );
}

function QuestionRow({
  q,
  primary,
  quota,
  onAdd,
  onRemove,
}: {
  q: PracticeQuestion;
  primary: boolean;
  quota: boolean;
  onAdd: () => void;
  onRemove: () => void;
}) {
  return (
    <li data-question={q.id} className="flex flex-col gap-2 border-t border-line py-4 first:border-t-0">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Badge variant="level">{q.origin === "bank" ? "Câu gốc" : "Câu sinh thêm"}</Badge>
        {q.status === "waiting" && (
          <a href="#" className="text-meta underline">
            Chờ học: mục {q.sectionLabel}
          </a>
        )}
        {q.status === "unlinked" && <span className="text-meta text-ink-soft">Chưa gắn mục · Câu {q.number}</span>}
      </div>
      <p id={`sum-${q.id}`} data-user className="m-0 wrap-anywhere">
        {q.summary}
      </p>
      {q.answerSource === "ai" && <Pen>đáp án do AI soạn</Pen>}
      <div className="flex flex-col items-stretch gap-1 sm:flex-row sm:flex-wrap sm:items-center">
        {q.status === "ready" && (
          <Button
            render={<a href={`/review/practice-${q.id}`} />}
            nativeButton={false}
            variant={primary ? "primary" : "secondary"}
            aria-describedby={`sum-${q.id}`}
            data-focus={`do-${q.id}`}
            className={FULL}
          >
            {COPY.doNow}
          </Button>
        )}
        {q.status === "ready" && (
          <Button
            variant="quiet"
            aria-describedby={quota ? `sum-${q.id} quota-note` : `sum-${q.id}`}
            aria-disabled={quota || undefined}
            onClick={quota ? undefined : onAdd}
          >
            {COPY.addMore}
          </Button>
        )}
        <Button variant="quiet" aria-describedby={`sum-${q.id}`} data-focus={`rm-${q.id}`} onClick={onRemove}>
          {COPY.remove}
        </Button>
      </div>
    </li>
  );
}

function RemovedRow({ q, onUndo }: { q: PracticeQuestion; onUndo: () => void }) {
  return (
    <li
      data-removed={q.id}
      className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line bg-sunken px-3 py-3 first:border-t-0"
    >
      <span>Đã gỡ khỏi luyện tập.</span>
      <Button variant="quiet" data-focus={`undo-${q.id}`} aria-describedby={`sum-${q.id}`} onClick={onUndo}>
        {COPY.undo}
      </Button>
      <span id={`sum-${q.id}`} data-user className="sr-only">
        {q.summary}
      </span>
    </li>
  );
}

/** What a practice result adds to GradeResult (which already shows the rubric per idea). */
export function PracticeResultExtras({
  timing,
  differsFromCard,
  answerSource,
}: {
  /** Only when the grade says the time is usable (timing_ok). */
  timing?: { seconds: number; refMinutes: number };
  differsFromCard?: { label: string; href: string };
  answerSource: "bank" | "ai";
}) {
  const minutes = timing ? Math.floor(timing.seconds / 60) : 0;
  const seconds = timing ? timing.seconds % 60 : 0;
  return (
    <div data-practice-extras className="mt-6.5 flex flex-col gap-3">
      {answerSource === "ai" && <Pen>đáp án do AI soạn</Pen>}
      {differsFromCard && (
        <p className="m-0 wrap-anywhere">
          Đáp án này khác với thẻ{" "}
          <a href={differsFromCard.href} className="underline">
            {differsFromCard.label}
          </a>
          .
        </p>
      )}
      {timing && (
        <p className="m-0 text-ink-soft">
          Bạn trả lời trong {minutes} phút{seconds ? ` ${seconds} giây` : ""}. Dạng này thường mất khoảng{" "}
          {timing.refMinutes} phút.
        </p>
      )}
    </div>
  );
}

const initialLive = (state: PracticeState) =>
  state === "loading"
    ? "Đang tải"
    : state === "importing"
      ? `Đang tách câu từ ${IMPORTED_FILE}…`
      : state === "removed"
        ? "Đã gỡ khỏi luyện tập."
        : "";

export function PracticeScreen({
  state,
  sections = SECTIONS,
  showTiming = true,
}: {
  state: PracticeState;
  sections?: StudiedSection[];
  showTiming?: boolean;
}) {
  const empty = state === "no-bank" || state === "loading" || state === "importing" || state === "error";
  const groups: PracticeGroup[] = empty ? [] : state === "empty-ready" ? WAITING_ONLY : GROUPS;
  const unlinked = groups.length > 0 && state !== "empty-ready" ? UNLINKED : [];
  const allRows = [...groups.flatMap((g) => g.questions), ...unlinked];
  const quota = state === "quota";

  const [removed, setRemoved] = useState<Record<string, "line" | "gone">>(state === "removed" ? { q12: "line" } : {});
  const [genFor, setGenFor] = useState<string | null>(state === "candidates" || state === "no-candidates" ? "g1" : null);
  const [pendingSection, setPendingSection] = useState<string | null>(null);
  const [sectionGen, setSectionGen] = useState<string | null>(null);
  const [decided, setDecided] = useState<Decisions>({});
  const [live, setLive] = useState(initialLive(state));
  const [focus, setFocus] = useState<string | null>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (state === "error") alertRef.current?.focus();
  }, [state]);
  useEffect(() => {
    if (!focus) return;
    const find = (key: string) => root.current?.querySelector<HTMLElement>(`[data-focus="${key}"]`);
    // A waiting or unlinked row has no "Làm câu này": focus falls back to its "Gỡ khỏi luyện tập".
    (find(focus) ?? find(focus.replace(/^do-/, "rm-")))?.focus();
  }, [focus, removed]);
  useEffect(() => {
    if (!pendingSection) return;
    const timer = setTimeout(() => {
      setSectionGen(pendingSection);
      setPendingSection(null);
    }, 600);
    return () => clearTimeout(timer);
  }, [pendingSection]);

  const gone = new Set(Object.keys(removed).filter((id) => removed[id] === "gone"));
  const removedAll = new Set(Object.keys(removed));
  const remove = (id: string) => {
    setRemoved((r) => {
      const next: Record<string, "line" | "gone"> = {};
      for (const key of Object.keys(r)) next[key] = "gone";
      next[id] = "line";
      return next;
    });
    setLive("Đã gỡ khỏi luyện tập.");
    setFocus(`undo-${id}`);
  };
  const undo = (id: string) => {
    setRemoved((r) => {
      const rest = { ...r };
      delete rest[id];
      return rest;
    });
    setLive("Đã đưa câu trở lại luyện tập.");
    setFocus(`do-${id}`);
  };
  const decide = (id: string, how: "kept" | "dropped") => {
    setDecided((d) => ({ ...d, [id]: how }));
    setLive(how === "kept" ? "Đã đưa vào luyện tập." : "Sẽ không nhắc lại câu này.");
  };

  const reviewOpen = genFor !== null || sectionGen !== null;
  const items = state === "no-candidates" && genFor !== null ? [] : CANDIDATES;
  const candidateOpen = reviewOpen && items.some((c) => !decided[c.id]);
  const owner = ownerFor(state, candidateOpen);
  const firstReady =
    groups.flatMap((g) => orderedRows(g.questions, gone)).find((r) => r.status === "ready" && !removedAll.has(r.id))?.id ??
    null;
  const studied = sections.filter((s) => s.studied);
  const notStudied = sections.length - studied.length;

  if (state === "result") {
    return (
      <div ref={root} className="mx-auto w-full max-w-180">
        <h1 className="m-0 mb-6 font-display text-title">
          <Marker>{COPY.heading}</Marker>
        </h1>
        <GradeResult result={RESULT} />
        <PracticeResultExtras
          timing={showTiming ? RESULT_EXTRAS.timing : undefined}
          differsFromCard={RESULT_EXTRAS.differsFromCard}
          answerSource={RESULT_EXTRAS.answerSource}
        />
        <div className="mt-8">
          <Button className={FULL}>{COPY.next}</Button>
        </div>
      </div>
    );
  }

  return (
    <div ref={root} className="mx-auto w-full max-w-180">
      <a href={`/subjects/${SUBJECT.id}`} className="text-meta text-ink-soft underline wrap-anywhere">
        ← {SUBJECT.name}
      </a>
      <h1 className="m-0 mt-3 font-display text-title">
        <Marker>{COPY.heading}</Marker>
      </h1>
      <p className="m-0 mt-1 text-read text-ink-soft wrap-anywhere">{SUBJECT.name}</p>
      <p role="status" className="sr-only">
        {live}
      </p>

      {state !== "loading" && state !== "error" && (
        <div className="mt-5">
          <Input readOnly aria-disabled="true" aria-label="Thanh lệnh" placeholder="Thanh lệnh" />
        </div>
      )}

      {state === "loading" && (
        <>
          <p aria-hidden="true" className="m-0 mt-6 text-ink-soft">
            Đang tải
          </p>
          <Skeleton />
        </>
      )}

      {state === "importing" && (
        <>
          <p aria-hidden="true" className="m-0 mt-6">
            Đang tách câu từ {IMPORTED_FILE}…
          </p>
          <Skeleton />
        </>
      )}

      {state === "error" && (
        <div
          ref={alertRef}
          tabIndex={-1}
          role="alert"
          className="mt-6 flex flex-col items-start gap-4 rounded-control bg-sunken p-4 outline-none"
        >
          <p className="m-0">Không tải được bộ câu hỏi.</p>
          <Button variant={owner === "retry" ? "primary" : "secondary"}>{COPY.retry}</Button>
        </div>
      )}

      {state === "imported" && (
        <Sheet variant="sunken" className="mt-6">
          <p className="m-0">{IMPORTED_NOTE}</p>
          <Button
            render={<a href="#danh-sach" />}
            nativeButton={false}
            variant={owner === "view" ? "primary" : "secondary"}
            className={`mt-3 ${FULL}`}
          >
            {COPY.view}
          </Button>
        </Sheet>
      )}

      {state === "no-bank" && (
        <section className="mt-6" aria-labelledby="nobank">
          <Sheet>
            <h2 id="nobank" className="sr-only">
              Chưa có bộ câu hỏi
            </h2>
            <p className="m-0">
              Chưa có bộ câu hỏi. Tải đề cương ôn, đề năm trước hoặc bộ câu hỏi thầy cô cho để luyện đúng dạng đề thi.
              Bạn vẫn luyện được bằng câu sinh thêm.
            </p>
            <Button
              render={<a href={`/subjects/${SUBJECT.id}`} />}
              nativeButton={false}
              variant={owner === "upload" ? "primary" : "secondary"}
              className={`mt-4 ${FULL}`}
            >
              {COPY.upload}
            </Button>
          </Sheet>
          <h2 className="m-0 mt-8 text-read font-semibold">Câu luyện tập theo mục</h2>
          {studied.length === 0 ? (
            <p className="m-0 mt-3">Chưa có mục nào học xong. Hoàn thành một buổi học để sinh câu luyện tập.</p>
          ) : (
            <ul className="m-0 mt-3 flex list-none flex-col gap-3 p-0">
              {studied.map((s) => (
                <li
                  key={s.id}
                  className="flex flex-col gap-2 border-t border-line pt-3 first:border-t-0 first:pt-0 sm:flex-row sm:items-center sm:justify-between"
                >
                  <span id={`sec-${s.id}`} data-user className="wrap-anywhere">
                    {s.label}
                  </span>
                  <Button
                    variant="secondary"
                    pending={pendingSection === s.id}
                    aria-disabled={(pendingSection !== null && pendingSection !== s.id) || undefined}
                    aria-describedby={`sec-${s.id}`}
                    className={FULL}
                    onClick={() => pendingSection === null && setPendingSection(s.id)}
                  >
                    {COPY.generate}
                  </Button>
                </li>
              ))}
            </ul>
          )}
          {notStudied > 0 && (
            <p className="m-0 mt-4 text-meta text-ink-soft">{notStudied} mục chưa học xong: học xong mới sinh câu.</p>
          )}
          {sectionGen && (
            <CandidateReview
              title={sections.find((s) => s.id === sectionGen)?.label ?? ""}
              items={CANDIDATES}
              decided={decided}
              primaryOn
              onClose={() => setSectionGen(null)}
              onDecide={decide}
            />
          )}
        </section>
      )}

      {quota && (
        <p id="quota-note" className="m-0 mt-5 rounded-control bg-sunken px-4 py-3 text-meta">
          Tạm hết lượt AI nên chưa sinh thêm câu được. Câu đã có vẫn làm được.
        </p>
      )}

      {groups.length > 0 && (
        <div id="danh-sach" className="mt-6">
          {state === "empty-ready" ? (
            <>
              <p className="m-0">Chưa có câu sẵn sàng. Câu sẽ sẵn sàng khi bạn học xong mục của nó.</p>
              <Button
                render={<a href={`/subjects/${SUBJECT.id}/sessions/new`} />}
                nativeButton={false}
                variant={owner === "session" ? "primary" : "secondary"}
                className={`mt-4 ${FULL}`}
              >
                {COPY.study}
              </Button>
            </>
          ) : (
            <p className="m-0 text-read">{summaryLine(allRows, removedAll)}</p>
          )}
          {groups.map((g) => (
            <section key={g.id} aria-labelledby={`g-${g.id}`} className="mt-8">
              <h2
                id={`g-${g.id}`}
                tabIndex={-1}
                data-focus={`group-${g.id}`}
                className="m-0 text-read font-semibold wrap-anywhere"
              >
                <span data-user>{g.name}</span> {g.suggested && <Pen>gợi ý</Pen>}
              </h2>
              <p className="m-0 mt-1 text-meta text-ink-soft">{masteryText(g.mastery)}</p>
              {showTiming && <p className="m-0 text-meta text-ink-soft">{timingLine(g.timing)}</p>}
              <ul className="m-0 mt-3 flex list-none flex-col p-0">
                {orderedRows(g.questions, gone).map((q) =>
                  removed[q.id] === "line" ? (
                    <RemovedRow key={q.id} q={q} onUndo={() => undo(q.id)} />
                  ) : (
                    <QuestionRow
                      key={q.id}
                      q={q}
                      primary={owner === "row" && firstReady === q.id}
                      quota={quota}
                      onAdd={() => setGenFor(g.id)}
                      onRemove={() => remove(q.id)}
                    />
                  ),
                )}
              </ul>
              {genFor === g.id && (
                <CandidateReview
                  title={g.name}
                  items={items}
                  decided={decided}
                  primaryOn
                  onClose={() => setGenFor(null)}
                  onDecide={decide}
                />
              )}
            </section>
          ))}
          {unlinked.length > 0 && (
            <section aria-labelledby="unlinked" className="mt-8">
              <h2 id="unlinked" className="m-0 text-read font-semibold">
                Chưa gắn mục
              </h2>
              <p className="m-0 mt-1 text-meta text-ink-soft">Sửa bằng thanh lệnh: gắn câu 7 với mục 3.4.</p>
              <ul className="m-0 mt-3 flex list-none flex-col p-0">
                {orderedRows(unlinked, gone).map((q) =>
                  removed[q.id] === "line" ? (
                    <RemovedRow key={q.id} q={q} onUndo={() => undo(q.id)} />
                  ) : (
                    <QuestionRow
                      key={q.id}
                      q={q}
                      primary={false}
                      quota={quota}
                      onAdd={() => undefined}
                      onRemove={() => remove(q.id)}
                    />
                  ),
                )}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
