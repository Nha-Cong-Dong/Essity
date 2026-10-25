"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AnswerBox, clock, type SaveState } from "@/components/review/answer-box";
import { GradeResult } from "@/components/review/grade-result";
import { FocusShell } from "@/components/shells";
import { Button } from "@/components/ui/button";
import { clearDraft, pickDraft, readDraft, writeDraft } from "@/lib/draft";
import { go } from "@/lib/navigate";
import { type AttemptView, type Current, reviewApi, type ReviewApi } from "@/lib/review-client";

// T2.15, T2.13 (US-04, US-05, US-08; DESIGN.md §6.4, §6.5; plan t2.15-t2.13-t2.16-answer-grade.md):
// one question at a time in the focus frame, "Hai cột yên": the question and the answer on the
// left, the result on the right. The draft is kept on this device at every keystroke and in
// core-api after a pause; submitting grades at once. A failed grading keeps the answer and offers
// "Chấm lại", never blocking "Câu tiếp" (D-7). The last question and "Dừng tại đây" close the
// session and go to /today (D-8).

/** PLAN T2.15: the draft goes to core-api once typing pauses this long. */
const SAVE_AFTER_MS = 1500;
/** A grading another request is running (plan 🟡9) is read again this often... */
const POLL_MS = 2000;
/** ...this many times, then the screen says to go on (DESIGN.md §6.5). */
const POLLS = 8;

type Sent = {
  text: string;
  dontRemember: boolean;
  /** null while core-api has not answered the submit. */
  view: AttemptView | null;
  /** Still grading after every read: the answer is saved, go on. */
  late: boolean;
};

type Phase =
  | { kind: "loading" }
  | { kind: "load_failed" }
  | { kind: "ended" }
  | { kind: "done"; ungraded: string[] }
  | { kind: "question"; step: Current; attemptId: string };

const ENDED = new Set(["session_ended", "session_not_found", "attempt_not_found"]);

export function ReviewScreen({ sessionId, api = reviewApi }: { sessionId: string; api?: ReviewApi }) {
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [text, setText] = useState("");
  const [save, setSave] = useState<{ state: SaveState; at: number | null }>({ state: "idle", at: null });
  const [sent, setSent] = useState<Sent | null>(null);
  const [sendFailed, setSendFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState({ position: 0, total: 0 });

  // What the timers and late answers compare against: the attempt on screen and its text now.
  const attemptRef = useRef<string | null>(null);
  const textRef = useRef("");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const finish = useCallback(async () => {
    setBusy(true);
    await api.stop(sessionId); // a failure still leaves: T2.9 closes a finished session itself
    go("/today");
  }, [api, sessionId]);

  const saveNow = useCallback(
    async (attemptId: string, value: string) => {
      setSave({ state: "saving", at: null });
      const reply = await api.saveDraft(attemptId, { answer_text: value, dont_remember: false });
      if (attemptRef.current !== attemptId) return;
      if (reply.ok) {
        if (textRef.current === value) {
          writeDraft(attemptId, { text: value, dontRemember: false, synced: true });
          setSave({ state: "saved", at: Date.now() });
        }
      } else if (reply.error === "session_ended") {
        setPhase({ kind: "ended" });
      } else if (reply.error !== "attempt_submitted") {
        setSave({ state: "local", at: null }); // never an error here (US-04 AC3)
      }
    },
    [api],
  );

  const show = useCallback(
    (step: Current, attemptId: string, server: { answer_text: string; dont_remember: boolean }) => {
      const local = readDraft(attemptId);
      const start = pickDraft(local, server);
      attemptRef.current = attemptId;
      textRef.current = start.text;
      setText(start.text);
      setSent(null);
      setSendFailed(false);
      setSave({ state: "idle", at: null });
      setLast({ position: step.position, total: step.total });
      setPhase({ kind: "question", step, attemptId });
      if (local && !local.synced && local.text !== server.answer_text) void saveNow(attemptId, start.text);
    },
    [saveNow],
  );

  const load = useCallback(async () => {
    attemptRef.current = null;
    // Twice at most: the question may be answered in another tab between the two calls.
    for (let tries = 0; tries < 2; tries += 1) {
      const reply = await api.current(sessionId);
      if (!reply.ok) {
        setPhase({ kind: ENDED.has(reply.error) ? "ended" : "load_failed" });
        return;
      }
      const step = reply.data;
      if (step.done) {
        if (step.ungraded.length === 0) await finish();
        else setPhase({ kind: "done", ungraded: step.ungraded });
        return;
      }
      if (step.attempt) {
        show(step, step.attempt.id, step.attempt);
        return;
      }
      const opened = await api.open(sessionId);
      if (opened.ok) {
        show(step, opened.data.id, opened.data);
        return;
      }
      if (opened.error !== "session_done") {
        setPhase({ kind: ENDED.has(opened.error) ? "ended" : "load_failed" });
        return;
      }
    }
    setPhase({ kind: "load_failed" });
  }, [api, sessionId, finish, show]);

  /** "Câu tiếp" and "Thử lại": the next question replaces this one. */
  const reload = useCallback(() => {
    setPhase({ kind: "loading" });
    void load();
  }, [load]);

  useEffect(() => {
    queueMicrotask(() => void load());
    return () => clearTimeout(timer.current);
  }, [load]);

  // US-04 AC3: a draft left on this device while offline goes up once the connection is back.
  useEffect(() => {
    function online() {
      const attemptId = attemptRef.current;
      if (attemptId && readDraft(attemptId)?.synced === false) void saveNow(attemptId, textRef.current);
    }
    window.addEventListener("online", online);
    return () => window.removeEventListener("online", online);
  }, [saveNow]);

  function change(value: string) {
    const attemptId = attemptRef.current;
    if (!attemptId) return;
    textRef.current = value;
    setText(value);
    writeDraft(attemptId, { text: value, dontRemember: false, synced: false });
    clearTimeout(timer.current);
    timer.current = setTimeout(() => void saveNow(attemptId, value), SAVE_AFTER_MS);
  }

  async function submit(dontRemember: boolean) {
    const attemptId = attemptRef.current;
    if (!attemptId) return;
    clearTimeout(timer.current);
    setSendFailed(false);
    setSent({ text, dontRemember, view: null, late: false });
    const reply = await api.submit(attemptId, { answer_text: text, dont_remember: dontRemember });
    if (attemptRef.current !== attemptId) return;
    if (!reply.ok) {
      if (reply.error === "session_ended") setPhase({ kind: "ended" });
      setSent(null);
      setSendFailed(true); // the text stays in the box, and on this device
      return;
    }
    clearDraft(attemptId);
    setSent((before) => before && { ...before, view: reply.data });
  }

  async function regrade() {
    const attemptId = attemptRef.current;
    if (!attemptId) return;
    setBusy(true);
    const reply = await api.regrade(attemptId);
    setBusy(false);
    if (reply.ok && attemptRef.current === attemptId) {
      setSent((before) => before && { ...before, view: reply.data, late: false });
    }
  }

  // Plan 🟡9: "in_progress" means another request is grading this answer: read it again.
  const grading = sent?.view?.grading === "in_progress" && !sent.late;
  useEffect(() => {
    const attemptId = attemptRef.current;
    if (!grading || !attemptId) return;
    let polls = 0;
    let stopped = false;
    let wait: ReturnType<typeof setTimeout>;
    const poll = () => {
      wait = setTimeout(async () => {
        polls += 1;
        const reply = await api.read(attemptId);
        if (stopped || attemptRef.current !== attemptId) return;
        if (reply.ok && reply.data.grading !== "in_progress") {
          setSent((before) => before && { ...before, view: reply.data });
        } else if (polls >= POLLS) {
          setSent((before) => before && { ...before, late: true });
        } else {
          poll();
        }
      }, POLL_MS);
    };
    poll();
    return () => {
      stopped = true;
      clearTimeout(wait);
    };
  }, [grading, api]);

  const exit = (
    <button
      type="button"
      disabled={busy}
      onClick={() => void finish()}
      className="h-11 cursor-pointer border-0 bg-transparent px-2 text-meta text-ink-soft underline decoration-line-strong underline-offset-4 hover:text-ink"
    >
      Dừng tại đây
    </button>
  );

  const shell = (position: number, total: number, children: React.ReactNode) => (
    <FocusShell position={position} total={total} exit={exit}>
      {children}
    </FocusShell>
  );

  if (phase.kind === "loading") {
    return shell(
      last.position,
      last.total,
      <div aria-busy="true">
        <p className="sr-only" role="status">
          Đang tải câu hỏi.
        </p>
      </div>,
    );
  }
  if (phase.kind === "load_failed") {
    return shell(0, 0, <LoadFailed onRetry={reload} />);
  }
  if (phase.kind === "ended") {
    return shell(0, 0, <Ended busy={busy} onLeave={() => void finish()} />);
  }
  if (phase.kind === "done") {
    return shell(
      0,
      0,
      <Ungraded ids={phase.ungraded} api={api} busy={busy} onLeave={() => void finish()} />,
    );
  }

  const { step } = phase;
  const lastQuestion = step.position >= step.total;
  return shell(
    step.position,
    step.total,
    <div className="grid items-start gap-7 min-[901px]:grid-cols-2 min-[901px]:gap-16">
      <section className="min-w-0 min-[901px]:sticky min-[901px]:top-8" aria-labelledby="question">
        <p className="m-0 text-meta text-ink-soft wrap-anywhere">{step.question.subject.name}</p>
        <h1 id="question" className="m-0 mt-3.5 font-display text-question wrap-anywhere">
          {step.question.prompt}
        </h1>
        {sent ? (
          <Written sent={sent} />
        ) : (
          <>
            <AnswerBox
              id="answer"
              value={text}
              onChange={change}
              onSubmit={() => void submit(false)}
              onForgot={() => void submit(true)}
              save={save}
              pending={null}
            />
            {sendFailed && (
              <p role="alert" data-copy="tam" className="m-0 mt-4 text-meta">
                Chưa gửi được. Câu trả lời vẫn ở đây, bạn gửi lại nhé.
              </p>
            )}
          </>
        )}
      </section>
      <section className="min-w-0 min-[901px]:border-l min-[901px]:border-line min-[901px]:pl-8" aria-live="polite">
        <Rail
          sent={sent}
          busy={busy}
          lastQuestion={lastQuestion}
          onNext={reload}
          onRegrade={() => void regrade()}
        />
      </section>
    </div>,
  );
}

/** The answer once sent: read-only, upright pink, no ruled lines (DESIGN.md §3.4). */
function Written({ sent }: { sent: Sent }) {
  const at = sent.view?.submitted_at ? Date.parse(sent.view.submitted_at) : null;
  return (
    <>
      {sent.dontRemember ? (
        <p className="m-0 mt-5 font-hand text-read text-ink-soft">Bạn chọn Không nhớ.</p>
      ) : (
        <p className="m-0 mt-5 text-read whitespace-pre-wrap text-hong wrap-anywhere">{sent.text}</p>
      )}
      {at !== null && (
        <p className="m-0 mt-3 border-t border-line pt-3 text-meta text-ink-soft">
          <span data-copy="tam">Câu trả lời của bạn · đã lưu {clock(at)}</span>
        </p>
      )}
    </>
  );
}

function Rail({
  sent,
  busy,
  lastQuestion,
  onNext,
  onRegrade,
}: {
  sent: Sent | null;
  busy: boolean;
  /** Plan D-8: the last question's way on closes the session (T2.17's summary comes later). */
  lastQuestion: boolean;
  onNext: () => void;
  onRegrade: () => void;
}) {
  const primary = useRef<HTMLButtonElement>(null);
  const view = sent?.view ?? null;
  const settled = view !== null && (view.grading !== "in_progress" || sent?.late === true);
  // DESIGN.md §6.5: focus moves to the one primary button, so Enter goes on.
  useEffect(() => {
    if (settled) primary.current?.focus();
  }, [settled, view]);

  const next = (variant: "primary" | "quiet") =>
    lastQuestion ? (
      <Button
        ref={variant === "primary" ? primary : undefined}
        type="button"
        variant={variant}
        pending={busy && variant === "primary"}
        onClick={onNext}
        data-copy="tam"
      >
        Về trang chính
      </Button>
    ) : (
      <Button ref={variant === "primary" ? primary : undefined} type="button" variant={variant} onClick={onNext}>
        Câu tiếp
      </Button>
    );

  if (!sent) {
    return (
      <p className="m-0 pt-1.5 font-hand text-body text-pencil">
        <span data-copy="tam">kết quả hiện ở đây sau khi gửi</span>
      </p>
    );
  }
  if (view === null || (view.grading === "in_progress" && !sent.late)) {
    return (
      <div aria-busy="true">
        <div aria-hidden="true" className="flex flex-col gap-3.5">
          <span className="h-7.5 w-38 rounded-full bg-sunken" />
          <span className="h-3.5 w-2/5 rounded-full bg-sunken" />
          <span className="h-3.5 w-[85%] rounded-full bg-sunken" />
          <span className="h-3.5 w-[70%] rounded-full bg-sunken" />
          <span className="h-21 rounded-control bg-sunken" />
        </div>
        <p className="m-0 mt-4.5 text-ink-soft">Đang chấm dựa trên tài liệu của bạn…</p>
      </div>
    );
  }
  if (view.grading === "in_progress") {
    return (
      <>
        <Notice calm>Câu trả lời đã được lưu. Đang chấm, bạn cứ làm câu tiếp theo.</Notice>
        <div className="mt-9 flex flex-wrap items-center gap-2">{next("primary")}</div>
      </>
    );
  }
  if (view.grading === "failed") {
    return (
      <>
        <Notice calm={false}>
          {view.failure === "disabled" ? (
            <span data-copy="tam">Chấm bài đang tạm tắt. Câu trả lời của bạn đã được lưu.</span>
          ) : (
            <span data-copy="tam">Chưa chấm được. Câu trả lời của bạn đã được lưu.</span>
          )}
        </Notice>
        <div className="mt-9 flex flex-wrap items-center gap-2">
          <Button ref={primary} type="button" pending={busy} onClick={onRegrade}>
            Chấm lại
          </Button>
          {next("quiet")}
        </div>
      </>
    );
  }
  return (
    <>
      {view.result && <GradeResult result={view.result} />}
      <div className="mt-9 flex flex-wrap items-center gap-2">{next("primary")}</div>
    </>
  );
}

function Notice({ calm, children }: { calm: boolean; children: React.ReactNode }) {
  return (
    <div
      className={
        calm
          ? "flex items-start gap-3 rounded-control bg-sheet px-4.5 py-4 inset-ring-1 inset-ring-line"
          : "flex items-start gap-3 rounded-control bg-sheet px-4.5 py-4 shadow-[inset_3px_0_0_var(--partial)] inset-ring-1 inset-ring-line"
      }
    >
      <svg
        viewBox="0 0 24 24"
        aria-hidden="true"
        className={`mt-0.5 size-5 shrink-0 fill-none stroke-current stroke-[1.75] ${calm ? "text-ink-soft" : "text-partial"}`}
      >
        <circle cx="12" cy="12" r="9" />
        <path d="M12 8v5M12 16h.01" strokeLinecap="round" />
      </svg>
      <p className="m-0">{children}</p>
    </div>
  );
}

/** DESIGN.md §6.4: the question could not load. */
function LoadFailed({ onRetry }: { onRetry: () => void }) {
  return (
    <div role="alert" className="mx-auto w-full max-w-170">
      <Notice calm={false}>
        <b className="block">Không tải được câu tiếp theo.</b>
        <span className="mt-1 block text-ink-soft">Các câu trả lời trước đã được lưu.</span>
      </Notice>
      <Button type="button" variant="secondary" className="mt-4" onClick={onRetry}>
        Thử lại
      </Button>
    </div>
  );
}

function Ended({ busy, onLeave }: { busy: boolean; onLeave: () => void }) {
  return (
    <div className="mx-auto flex w-full max-w-170 flex-col items-start gap-4">
      <p data-copy="tam" className="m-0 text-read">
        Phiên ôn này đã kết thúc.
      </p>
      <Button type="button" pending={busy} onClick={onLeave} data-copy="tam">
        Về trang chính
      </Button>
    </div>
  );
}

/** Plan D-7: the session's answers left ungraded, each with "Chấm lại"; leaving is never blocked. */
function Ungraded({
  ids,
  api,
  busy,
  onLeave,
}: {
  ids: string[];
  api: ReviewApi;
  busy: boolean;
  onLeave: () => void;
}) {
  return (
    <div className="mx-auto flex w-full max-w-170 flex-col items-start gap-6">
      <h1 className="m-0 font-display text-lead">
        <span data-copy="tam">Còn {ids.length} câu chưa chấm</span>
      </h1>
      <ul className="m-0 flex w-full list-none flex-col gap-4 p-0">
        {ids.map((id) => (
          <UngradedRow key={id} id={id} api={api} />
        ))}
      </ul>
      <Button type="button" pending={busy} onClick={onLeave} data-copy="tam">
        Về trang chính
      </Button>
    </div>
  );
}

function UngradedRow({ id, api }: { id: string; api: ReviewApi }) {
  const [prompt, setPrompt] = useState<string | null>(null);
  const [state, setState] = useState<"idle" | "pending" | "graded" | "failed">("idle");

  useEffect(() => {
    let live = true;
    void api.read(id).then((reply) => {
      if (!live || !reply.ok) return;
      setPrompt(reply.data.question?.prompt ?? null);
      if (reply.data.grading === "graded") setState("graded");
    });
    return () => {
      live = false;
    };
  }, [api, id]);

  async function regrade() {
    setState("pending");
    const reply = await api.regrade(id);
    setState(reply.ok && reply.data.grading === "graded" ? "graded" : "failed");
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-4">
      <span className="min-w-0 flex-1 wrap-anywhere">{prompt ?? "…"}</span>
      {state === "graded" ? (
        <span data-copy="tam" className="text-meta text-ink-soft">
          Đã chấm
        </span>
      ) : (
        <span className="flex items-center gap-3">
          {state === "failed" && (
            <span data-copy="tam" className="text-meta text-ink-soft">
              Chưa chấm được
            </span>
          )}
          <Button type="button" variant="secondary" pending={state === "pending"} onClick={() => void regrade()}>
            Chấm lại
          </Button>
        </span>
      )}
    </li>
  );
}
