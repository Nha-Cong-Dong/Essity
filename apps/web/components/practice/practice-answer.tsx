"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Pen, PracticeResultExtras } from "@/components/practice/practice-extras";
import { AnswerBox, clock, type SaveState } from "@/components/review/answer-box";
import { GradeResult } from "@/components/review/grade-result";
import { Button } from "@/components/ui/button";
import { clearDraft, pickDraft, readDraft, writeDraft } from "@/lib/draft";
import { type PracticeApi, practiceApi, type PracticeView } from "@/lib/practice-client";
import type { Result } from "@/lib/review-client";

// T8.7 (US-16 AC2, AC3, AC5; DESIGN §6.12, D26-D27): answer one practice question. Used by the
// Luyện tập screen and by the Today review session when its current step is a practice question
// (T8.5 review F1). The draft is kept on this device and in core-api like US-04 AC3. The tab's
// hidden time is measured here and sent with the answer (`hidden_ms`); nothing about time is
// shown while writing (no clock, AC5). The result is the rubric (what is missing), the reference
// answer and a label when the AI wrote it; no score, no streak.

const SAVE_AFTER_MS = 1500;
const POLL_MS = 2000;
const POLLS = 8;

type Phase =
  | { kind: "loading" }
  | { kind: "failed" }
  | { kind: "gone" }
  | { kind: "writing"; view: PracticeView }
  | { kind: "sent"; view: PracticeView | null; prompt: string; text: string; dontRemember: boolean };

/** The API's practice result in the shape GradeResult draws: the rubric shows as "còn thiếu". */
export function toResult(view: PracticeView): Result | null {
  const r = view.result;
  if (!r) return null;
  return {
    grade_id: r.grade_id,
    overall: r.overall,
    missing: r.missing,
    understanding: null,
    // Every rubric point; GradeResult draws them (T8.7b). Met = "Đúng", not met = "Thiếu".
    units: r.units.map((u, index) => ({
      unit_id: String(index),
      title: u.text,
      verdict: u.met ? ("correct" as const) : ("incorrect" as const),
    })),
    reference_answer: r.reference_answer ?? "",
    sources: [],
    practice: true,
  };
}

export function PracticeAnswer({
  questionId,
  onNext,
  nextLabel = "Câu tiếp",
  api = practiceApi,
}: {
  questionId: string;
  /** "Câu tiếp": the caller shows what comes next. */
  onNext: () => void;
  nextLabel?: string;
  api?: PracticeApi;
}) {
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });
  const [text, setText] = useState("");
  const [save, setSave] = useState<{ state: SaveState; at: number | null }>({ state: "idle", at: null });
  const [sendFailed, setSendFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [removed, setRemoved] = useState(false);
  const [late, setLate] = useState(false);
  const [overrideMode, setOverrideMode] = useState<"idle" | "choosing" | "updated">("idle");
  const [overrideFailed, setOverrideFailed] = useState(false);

  const attemptRef = useRef<string | null>(null);
  const textRef = useRef("");
  const baseRef = useRef("");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  // US-16 AC5: the time the tab was hidden while this question was open. Never shown.
  const hiddenMs = useRef(0);
  const hiddenSince = useRef<number | null>(null);
  const nextButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    function onVisibility() {
      if (document.hidden) hiddenSince.current = Date.now();
      else if (hiddenSince.current !== null) {
        hiddenMs.current += Date.now() - hiddenSince.current;
        hiddenSince.current = null;
      }
    }
    if (document.hidden) hiddenSince.current = Date.now();
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  const saveNow = useCallback(
    async (attemptId: string, value: string) => {
      setSave({ state: "saving", at: null });
      const reply = await api.saveDraft(attemptId, { answer_text: value, dont_remember: false });
      if (attemptRef.current !== attemptId) return;
      if (reply.ok) {
        baseRef.current = value;
        if (textRef.current === value) {
          writeDraft(attemptId, { text: value, dontRemember: false, synced: true, base: value });
          setSave({ state: "saved", at: Date.now() });
        } else {
          writeDraft(attemptId, { text: textRef.current, dontRemember: false, synced: false, base: value });
        }
      } else if (reply.error !== "attempt_submitted") {
        setSave({ state: "local", at: null }); // never an error here (US-04 AC3)
      }
    },
    [api],
  );

  const load = useCallback(async () => {
    attemptRef.current = null;
    setPhase({ kind: "loading" });
    const reply = await api.open(questionId);
    if (!reply.ok) {
      setPhase({ kind: reply.error === "question_not_found" ? "gone" : "failed" });
      return;
    }
    const view = reply.data;
    attemptRef.current = view.attempt_id;
    if (view.status === "submitted") {
      setPhase({
        kind: "sent",
        view,
        prompt: view.question.prompt,
        text: view.answer_text ?? "",
        dontRemember: view.dont_remember,
      });
      return;
    }
    const server = { answer_text: view.answer_text ?? "", dont_remember: view.dont_remember };
    const local = readDraft(view.attempt_id);
    const start = pickDraft(local, server);
    baseRef.current = server.answer_text;
    textRef.current = start.text;
    setText(start.text);
    setPhase({ kind: "writing", view });
    if (local && !local.synced && start.text === local.text && local.text !== server.answer_text) {
      void saveNow(view.attempt_id, start.text);
    }
  }, [api, questionId, saveNow]);

  useEffect(() => {
    queueMicrotask(() => void load());
    return () => clearTimeout(timer.current);
  }, [load]);

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
    writeDraft(attemptId, { text: value, dontRemember: false, synced: false, base: baseRef.current });
    clearTimeout(timer.current);
    timer.current = setTimeout(() => void saveNow(attemptId, value), SAVE_AFTER_MS);
  }

  async function submit(dontRemember: boolean) {
    const attemptId = attemptRef.current;
    if (!attemptId || phase.kind !== "writing") return;
    clearTimeout(timer.current);
    setSendFailed(false);
    const ongoing = hiddenSince.current === null ? 0 : Date.now() - hiddenSince.current;
    const hidden_ms = Math.max(0, Math.round(hiddenMs.current + ongoing));
    const prompt = phase.view.question.prompt;
    const before = phase;
    setPhase({ kind: "sent", view: null, prompt, text, dontRemember });
    const reply = await api.submit(attemptId, {
      answer_text: dontRemember ? "" : text,
      dont_remember: dontRemember,
      hidden_ms,
    });
    if (attemptRef.current !== attemptId) return;
    if (!reply.ok) {
      setSendFailed(true); // the text stays in the box, and on this device
      setPhase(before);
      return;
    }
    clearDraft(attemptId);
    setPhase({ kind: "sent", view: reply.data, prompt, text, dontRemember });
  }

  async function regrade() {
    const attemptId = attemptRef.current;
    if (!attemptId) return;
    setBusy(true);
    setLate(false);
    const reply = await api.regrade(attemptId);
    setBusy(false);
    if (reply.ok && attemptRef.current === attemptId) {
      setPhase((was) => (was.kind === "sent" ? { ...was, view: reply.data } : was));
    }
  }

  // "Chấm sai" (US-09, US-16 AC10): the learner's own verdict is a new grade of this attempt; the
  // question's schedule is rebuilt from the last attempt's latest grade.
  async function override(verdict: "correct" | "incorrect") {
    const gradeId = phase.kind === "sent" ? phase.view?.result?.grade_id : undefined;
    if (!gradeId) return;
    setBusy(true);
    setOverrideFailed(false);
    const reply = await api.override(gradeId, verdict);
    setBusy(false);
    if (reply.ok) {
      setOverrideMode("updated");
      setPhase((was) => (was.kind === "sent" ? { ...was, view: reply.data } : was));
    } else {
      setOverrideFailed(true);
    }
  }

  // "Làm lại câu này": a new attempt at the same question; the old one and its grades stay.
  function redo() {
    hiddenMs.current = 0;
    hiddenSince.current = document.hidden ? Date.now() : null;
    textRef.current = "";
    setText("");
    setRemoved(false);
    setOverrideMode("idle");
    setOverrideFailed(false);
    void load();
  }

  async function remove() {
    const reply = await api.remove(questionId);
    if (reply.ok) setRemoved(true);
  }

  async function undoRemove() {
    const reply = await api.restore(questionId);
    if (reply.ok) setRemoved(false);
  }

  // The grade may be written by another request: read it again a few times, then say to go on.
  const view = phase.kind === "sent" ? phase.view : null;
  const waiting =
    view !== null && (view.grading === "in_progress" || view.grading === "pending") && view.result === null;
  useEffect(() => {
    const attemptId = attemptRef.current;
    if (!waiting || !attemptId) return;
    let polls = 0;
    let stopped = false;
    let wait: ReturnType<typeof setTimeout>;
    const poll = () => {
      wait = setTimeout(async () => {
        polls += 1;
        const reply = await api.read(attemptId);
        if (stopped || attemptRef.current !== attemptId) return;
        if (reply.ok && (reply.data.result !== null || reply.data.grading === "failed")) {
          setPhase((was) => (was.kind === "sent" ? { ...was, view: reply.data } : was));
        } else if (polls >= POLLS) {
          setLate(true);
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
  }, [waiting, api]);

  const settled = phase.kind === "sent" && view !== null && (!waiting || late);
  useEffect(() => {
    if (settled) nextButton.current?.focus();
  }, [settled]);

  const wrap = "mx-auto w-full max-w-180";
  if (phase.kind === "loading") {
    return (
      <div className={wrap} aria-busy="true">
        <p role="status" className="sr-only">
          Đang tải câu hỏi.
        </p>
      </div>
    );
  }
  if (phase.kind === "failed" || phase.kind === "gone") {
    return (
      <div className={wrap} role="alert">
        <p className="m-0">{phase.kind === "gone" ? "Câu này không còn trong luyện tập." : "Không tải được câu hỏi."}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          {phase.kind === "failed" && (
            <Button variant="secondary" onClick={() => void load()}>
              Thử lại
            </Button>
          )}
          <Button variant={phase.kind === "gone" ? "primary" : "quiet"} onClick={onNext}>
            {nextLabel}
          </Button>
        </div>
      </div>
    );
  }

  const prompt = phase.kind === "writing" ? phase.view.question.prompt : phase.prompt;
  const result = view ? toResult(view) : null;
  return (
    <div className={wrap} data-practice-answer>
      <p className="m-0 text-meta text-ink-soft">Luyện tập</p>
      <h1 data-user className="m-0 mt-3.5 font-display text-question wrap-anywhere">
        {prompt}
      </h1>
      {phase.kind === "writing" ? (
        <>
          <AnswerBox
            id="practice-answer"
            value={text}
            onChange={change}
            onSubmit={() => void submit(false)}
            onForgot={() => void submit(true)}
            save={save}
            pending={null}
          />
          {sendFailed && (
            <p role="alert" className="m-0 mt-4 text-meta">
              Chưa gửi được. Câu trả lời vẫn ở đây, bạn gửi lại nhé.
            </p>
          )}
        </>
      ) : (
        <>
          {phase.dontRemember ? (
            <p className="m-0 mt-5 font-hand text-read text-ink-soft">Bạn chọn Không nhớ.</p>
          ) : (
            <p className="m-0 mt-5 text-read whitespace-pre-wrap text-hong wrap-anywhere">{phase.text}</p>
          )}
          {view?.submitted_at && (
            <p className="m-0 mt-3 border-t border-line pt-3 text-meta text-ink-soft">
              Câu trả lời của bạn · đã lưu {clock(Date.parse(view.submitted_at))}
            </p>
          )}
          <div className="mt-8" aria-live="polite">
            {view === null || (waiting && !late) ? (
              <div aria-busy="true">
                <p className="m-0 text-ink-soft">Đang chấm dựa trên tài liệu của bạn…</p>
              </div>
            ) : result && view ? (
              <>
                <GradeResult result={result} />
                <PracticeResultExtras
                  answerSource={view.result?.answer_origin === "ai" ? "ai" : "bank"}
                  differsFromCard={view.result?.differs_from_card_id ? true : undefined}
                />
                {overrideMode === "updated" && (
                  <p role="status" className="m-0 mt-6 rounded-control bg-sunken px-4 py-3 text-meta">
                    Đã cập nhật kết quả và lịch ôn.
                  </p>
                )}
                {overrideFailed && (
                  <p role="alert" className="m-0 mt-4 text-meta">
                    Chưa gửi được. Bạn bấm lại nhé.
                  </p>
                )}
                <div className="mt-8 flex flex-wrap items-center gap-2">
                  <Button ref={nextButton} onClick={onNext} className="max-sm:w-full">
                    {nextLabel}
                  </Button>
                  <Button variant="secondary" onClick={redo}>
                    Làm lại câu này
                  </Button>
                  {overrideMode === "choosing" ? (
                    <>
                      <Button variant="secondary" pending={busy} onClick={() => void override("correct")}>
                        Thực ra tôi đúng
                      </Button>
                      <Button variant="secondary" pending={busy} onClick={() => void override("incorrect")}>
                        Thực ra tôi sai
                      </Button>
                    </>
                  ) : (
                    <Button variant="quiet" onClick={() => setOverrideMode("choosing")}>
                      Chấm sai
                    </Button>
                  )}
                  {removed ? (
                    <>
                      <Pen>Đã gỡ khỏi luyện tập.</Pen>
                      <Button variant="quiet" onClick={() => void undoRemove()}>
                        Hoàn tác
                      </Button>
                    </>
                  ) : (
                    <Button variant="quiet" onClick={() => void remove()}>
                      Gỡ khỏi luyện tập
                    </Button>
                  )}
                </div>
              </>
            ) : (
              <>
                <p className="m-0">
                  {view.grading === "failed"
                    ? "Chưa chấm được. Câu trả lời của bạn đã được lưu."
                    : "Câu trả lời đã được lưu. Đang chấm, bạn cứ làm câu tiếp theo."}
                </p>
                <div className="mt-6 flex flex-wrap items-center gap-2">
                  {view.grading === "failed" ? (
                    <>
                      <Button pending={busy} onClick={() => void regrade()}>
                        Chấm lại
                      </Button>
                      <Button ref={nextButton} variant="quiet" onClick={onNext}>
                        {nextLabel}
                      </Button>
                    </>
                  ) : (
                    <Button ref={nextButton} onClick={onNext}>
                      {nextLabel}
                    </Button>
                  )}
                </div>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
