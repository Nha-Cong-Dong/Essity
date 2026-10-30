"use client";

import Link from "next/link";
import { useEffect, useReducer, useRef, useState } from "react";

import { FieldHint } from "@/components/field-error";
import { FocusShell } from "@/components/shells";
import { Button, buttonVariants } from "@/components/ui/button";
import type { FileRow, Suggestion } from "@/lib/fixtures/session-study";
import { type Draft, draftsReducer } from "@/lib/session-study/drafts";
import type { DocRef, Mention } from "@/lib/session-study/mention";
import { type Round, roundReducer } from "@/lib/session-study/round";

import { FileDrop } from "./session-file-drop";
import { MentionBox } from "./session-mention-box";
import { DoneLine, Region } from "./session-parts";
import { ProcessingArea } from "./session-processing";
import { ReviewArea, type ScopeRow } from "./session-review";
import { SavedArea, type SavedKind } from "./session-saved";

// T7.12a (US-02, US-02b; DESIGN.md §6.7; docs in .work/T7.12a/design-decisions.md): the whole study
// session on one screen: suggestion, submission, reading, cards, "Học tiếp hay dừng?". One round
// is a list of areas; the one being worked on is open and a finished one folds into a line. No API
// here: the caller gives the data and, in the preview, decides how a send ends. T7.12 wires it.

export type SessionInitial = {
  round: Round;
  drafts: Draft[];
  text: string;
  mentions: Mention[];
  files: FileRow[];
  scope: ScopeRow[];
  saved: SavedKind;
  /** Opened again from "Tiếp tục": drafts were kept. */
  resumed: boolean;
  tooManyPages?: { total: number; read: number } | null;
};

export type SessionScreenProps = {
  subject: string;
  stopHref: string;
  docs: DocRef[];
  suggestion: Suggestion;
  nextSuggestion: Suggestion;
  initial: SessionInitial;
  /** Preview only: a send runs on to its cards by itself after a moment. */
  autoAdvance?: boolean;
  /** The cards a finished read produces. */
  readDrafts: () => Draft[];
  /** What the server holds when a card was changed elsewhere (409, "Tải lại thẻ"). */
  serverDraft: Draft;
};

const kindOf = (name: string): FileRow["kind"] =>
  /\.(jpe?g|png|heic|webp)$/i.test(name) ? "image" : /\.pdf$/i.test(name) ? "pdf" : /\.docx$/i.test(name) ? "docx" : /\.pptx$/i.test(name) ? "pptx" : "text";

function Suggest({ suggestion, id }: { suggestion: Suggestion; id: string }) {
  const [why, setWhy] = useState(false);
  return (
    <Region phase={id} title={suggestion.text}>
      {suggestion.kind === "section" && (
        <>
          <p className="m-0 text-body text-ink-soft">{suggestion.reason}</p>
          <div className="flex flex-col items-start gap-2">
            <button
              type="button"
              aria-expanded={why}
              onClick={() => setWhy((value) => !value)}
              className="min-h-11 text-body underline decoration-line-strong decoration-[1.5px] underline-offset-[5px]"
            >
              Vì sao mục này?
            </button>
            {why && <p className="m-0 w-full rounded-control bg-sunken p-4 text-body">{suggestion.pace}</p>}
          </div>
        </>
      )}
    </Region>
  );
}

export function SessionScreen(props: SessionScreenProps) {
  const { subject, stopHref, docs, initial } = props;
  const [round, send] = useReducer(roundReducer, initial.round);
  const [drafts, dispatch] = useReducer(draftsReducer, initial.drafts);
  const [text, setText] = useState(initial.text);
  const [mentions, setMentions] = useState(initial.mentions);
  const [files, setFiles] = useState(initial.files);
  const [scope, setScope] = useState(initial.scope);
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  const [free, setFree] = useState(props.suggestion.kind === "free");
  const counter = useRef(0);
  const timers = useRef<number[]>([]);

  const newId = () => `new-${++counter.current}`;
  const say = (value: string) => setNote(value);
  const later = (ms: number, run: () => void) => {
    timers.current.push(window.setTimeout(run, ms));
  };
  useEffect(() => () => timers.current.forEach((t) => window.clearTimeout(t)), []);

  // Focus follows the user's own action only (design decision C5); a background change has none.
  useEffect(() => {
    if (round.focus) document.getElementById(`session-h-${round.focus}`)?.focus();
  }, [round]);

  const uploading = files.filter((f) => f.state === "uploading").length;
  const usableFiles = files.filter((f) => f.state === "done").length;
  const suggestion = round.round > 1 ? props.nextSuggestion : props.suggestion;
  const isFree = free && round.round === 1;

  function finishRead() {
    dispatch({ type: "clear" });
    dispatch({ type: "append-ai", drafts: props.readDrafts() });
    setScope(isFree ? [] : mentions.length > 0 ? mentions.map((m) => ({ id: `${m.docId}`, doc: m.name, from: 52, to: 58 })) : [{ id: "textbook", doc: "Giáo trình", from: 52, to: 58 }]);
    send({ type: "drafts-ready", count: props.readDrafts().length });
  }

  function submit() {
    if (uploading > 0) return;
    if (text.trim() === "" && usableFiles === 0) {
      setProblem("Thêm ít nhất một file hoặc vài dòng mô tả.");
      return;
    }
    setProblem(null);
    setNote("");
    send({ type: "send" });
    if (props.autoAdvance) {
      later(600, () => send({ type: "processing" }));
      later(1600, finishRead);
    }
  }

  function save() {
    const hit = drafts.find((d) => d.status === "draft" && d.conflict);
    if (hit) {
      say("Có thẻ đã đổi ở nơi khác. Tải lại thẻ trước khi lưu.");
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      document.getElementById(`session-card-${hit.id}`)?.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
      return;
    }
    setSaving(true);
    later(500, () => {
      setSaving(false);
      send({ type: "save-ok" });
    });
  }

  function reload(id: string) {
    const current = drafts.find((d) => d.id === id);
    if (!current) return;
    const server = props.serverDraft.id === id ? props.serverDraft : { ...current, version: current.version + 1 };
    dispatch({ type: "reload", draft: server });
  }

  const savedCount = drafts.filter((d) => d.status === "draft" && (d.title.trim() || d.summary.trim())).length;
  const exit =
    round.phase === "saved" ? null : (
      <Link href={stopHref} className={buttonVariants({ variant: "quiet" })}>
        Dừng
      </Link>
    );

  return (
    <FocusShell position={0} total={0} exit={exit} title={<span title={subject}>{subject}</span>}>
      <div className="mx-auto flex w-full max-w-(--col-session) flex-col gap-10">
        <p className="sr-only" role="status" aria-live="polite">
          {note || round.announce}
        </p>
        {initial.resumed && (
          <p className="m-0 text-meta text-ink-soft">Buổi học đang dở: các thẻ nháp của bạn được giữ.</p>
        )}
        {history.map((line) => (
          <DoneLine key={line} label={line} />
        ))}

        {round.phase === "compose" ? (
          <>
            <Suggest suggestion={isFree ? { kind: "free", text: "Buổi học tự do. Bài nộp không gắn mục đề cương." } : suggestion} id="suggest" />
            <Region phase="compose" title="Bạn đã học gì?">
              <MentionBox
                value={text}
                mentions={mentions}
                docs={docs}
                say={say}
                rejectedDoc={round.rejectedDoc}
                problem={problem}
                onChange={(value, next) => {
                  setText(value);
                  setMentions(next);
                  setProblem(null);
                }}
              />
              <FileDrop
                rows={files}
                tooManyPages={initial.tooManyPages}
                onAdd={(added) =>
                  setFiles((rows) => [
                    ...rows,
                    ...added.map((file) => ({ id: newId(), name: file.name, kind: kindOf(file.name), state: "done" as const })),
                  ])
                }
                onRemove={(id) => setFiles((rows) => rows.filter((row) => row.id !== id))}
                onRetry={(id) => setFiles((rows) => rows.map((row) => (row.id === id ? { ...row, state: "done" as const } : row)))}
              />
              <div className="flex flex-col items-start gap-2">
                <Button
                  type="button"
                  className="max-[480px]:w-full"
                  aria-disabled={uploading > 0 || undefined}
                  aria-describedby={uploading > 0 ? "session-send-why" : undefined}
                  onClick={submit}
                >
                  Gửi
                </Button>
                {uploading > 0 && (
                  <span id="session-send-why">
                    <FieldHint id="session-send-hint">Đang tải {uploading} file…</FieldHint>
                  </span>
                )}
              </div>
              {isFree ? null : (
                <button
                  type="button"
                  onClick={() => setFree(true)}
                  className="min-h-11 self-start text-body underline decoration-line-strong decoration-[1.5px] underline-offset-[5px]"
                >
                  Học tự do
                </button>
              )}
            </Region>
          </>
        ) : (
          <>
            <DoneLine label={isFree ? "Gợi ý: học tự do" : `Gợi ý: ${suggestion.kind === "section" ? "mục 3.2 TCP flow control" : "học tự do"}`} />
            <DoneLine label={`Bài nộp: ${files.length} file, ${text.trim() ? 1 : 0} mô tả`}>
              {text.trim() ? <span className="whitespace-pre-line">{text}</span> : null}
            </DoneLine>
          </>
        )}

        {round.phase === "processing" && round.submission && (
          <Region phase="processing" title="Đang đọc bài nộp">
            <ProcessingArea submission={round.submission} onRetry={() => send({ type: "retry" })} onManual={() => send({ type: "manual" })} />
          </Region>
        )}

        {round.phase === "review" && (
          <Region phase="review" title="Thẻ nháp">
            <ReviewArea
              drafts={drafts}
              dispatch={dispatch}
              scope={scope}
              partialNote={round.partialNote}
              saveError={round.saveError}
              saving={saving}
              newId={newId}
              onSave={save}
              onRetryRead={() => send({ type: "retry" })}
              onReload={reload}
              lateCount={0}
              say={say}
            />
          </Region>
        )}

        {round.phase === "saved" && (
          <>
            <DoneLine label={`Đã lưu ${savedCount} thẻ`} />
            <Region phase="saved" title="Đã lưu">
              <SavedArea
                kind={isFree ? "free" : initial.saved}
                count={savedCount}
                stopHref={stopHref}
                onContinue={() => {
                  setHistory((lines) => [...lines, `Vòng ${round.round}: đã lưu ${savedCount} thẻ`]);
                  dispatch({ type: "clear" });
                  setText("");
                  setMentions([]);
                  setFiles([]);
                  setFree(false);
                  send({ type: "continue" });
                }}
              />
            </Region>
          </>
        )}
      </div>
    </FocusShell>
  );
}
