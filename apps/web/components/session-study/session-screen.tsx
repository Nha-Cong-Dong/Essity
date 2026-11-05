"use client";

import Link from "next/link";
import { type ReactNode, useEffect, useReducer, useRef, useState } from "react";

import { FieldHint } from "@/components/field-error";
import { FocusShell } from "@/components/shells";
import { Button, buttonVariants } from "@/components/ui/button";
import type { FileRow, Suggestion } from "@/lib/fixtures/session-study";
import { type FileRef, rowStateOf } from "@/lib/session-study/files";
import { uploadPdf } from "@/lib/upload-client";
import type { Piece, SessionApi } from "@/lib/session-study/api";
import { rememberPendingSession } from "@/lib/session-study/pending";
import { appendMention, type DocRef, type Mention } from "@/lib/session-study/mention";
import { type Round, roundReducer, type SessionResult } from "@/lib/session-study/round";

import { FileDrop } from "./session-file-drop";
import { MentionBox } from "./session-mention-box";
import { DoneLine, Region } from "./session-parts";
import { ProcessingArea } from "./session-processing";
import { SessionEndDialog } from "./session-end-dialog";
import { DoneArea } from "./session-saved";

// T7.12a (US-02, US-02b; DESIGN.md §6.7; docs in .work/T7.12a/design-decisions.md): the whole study
// session on one screen: suggestion, submission, reading, result, "Học tiếp hay dừng?". CARDS-V3:
// the cards go straight to the Kho, so the result is a confirmation, not a list to approve. One round
// is a list of areas; the one being worked on is open and a finished one folds into a line. No API
// here: the caller gives the data and, in the preview, decides how a send ends. T7.12 wires it.

export type SessionInitial = {
  round: Round;
  text: string;
  mentions: Mention[];
  files: FileRow[];
  tooManyPages?: { total: number; read: number } | null;
};

export type SessionScreenProps = {
  subject: string;
  /** F3: where the "cards are ready" toast leads (the subject's area of the knowledge store). */
  subjectId?: string;
  /** The preview: "Hoàn thành" stays on this screen, which then shows the reading and the cards. */
  stayOnComplete?: boolean;
  stopHref: string;
  docs: DocRef[];
  suggestion: Suggestion;
  nextSuggestion: Suggestion;
  initial: SessionInitial;
  /** Preview only: a send runs on to its cards by itself after a moment. */
  autoAdvance?: boolean;
  /** The result a finished read produces (the preview). */
  readResult?: () => SessionResult;
  /** T7.12: core-api behind the screen. Without it (the preview) the screen runs on its own. */
  api?: SessionApi;
  /** T7.12d: shown under the areas of the round (the subject's cards by section). */
  footer?: ReactNode;
};

/** T7.12: how long the reading is asked about while it runs (a retry after a hiccup is the same). */
const POLL_MS = 2500;
export const SUBMIT_COPY = {
  network: "Chưa gửi được, mạng đang chập chờn. Câu của bạn vẫn được giữ, thử gửi lại.",
  tooLong: "Câu mô tả dài quá. Rút gọn bớt rồi gửi lại.",
  nothing: "Chưa có gì để gửi. Viết vài dòng hoặc thêm file rồi gửi.",
  mention: "Chưa hiểu một chỗ @ trong câu. Xem chỗ được đánh dấu rồi gửi lại.",
  mentionPiece: "Có một chỗ @ không khớp tài liệu nào. Bỏ phần có chỗ @ đó (hoặc ghi lại phần mới) rồi bấm Kết thúc buổi học.",
  closed: "Buổi này đã được gửi đi rồi.",
  other: "Chưa hoàn thành được. Thử lại sau ít phút.",
} as const;

/** What to tell the learner when handing a session in (or dropping a piece) fails: by the code,
 * not "network" for everything (only a dropped connection, status 0, is the network). */
export function completeProblem(status: number, error: string): string {
  if (status === 0) return SUBMIT_COPY.network;
  if (error.startsWith("mention_") || error.startsWith("scope_") || error === "document_not_found") return SUBMIT_COPY.mentionPiece;
  if (error === "nothing_submitted") return SUBMIT_COPY.nothing;
  if (error === "text_too_long") return SUBMIT_COPY.tooLong;
  if (error === "session_confirmed") return SUBMIT_COPY.closed;
  return SUBMIT_COPY.other;
}

const kindOf = (name: string): FileRow["kind"] =>
  /\.(jpe?g|png|heic|webp)$/i.test(name) ? "image" : /\.pdf$/i.test(name) ? "pdf" : /\.docx$/i.test(name) ? "docx" : /\.pptx$/i.test(name) ? "pptx" : "text";

function Suggest({ suggestion, id }: { suggestion: Suggestion; id: string }) {
  const [why, setWhy] = useState(false);
  if (suggestion.kind !== "section") {
    return <p className="m-0 -mt-6 text-body text-ink-soft">{suggestion.text}</p>;
  }
  return (
    <Region phase={id} title={suggestion.text}>
      {suggestion.kind === "section" && (
        <>
          <div className="flex flex-col items-start gap-2">
            <button
              type="button"
              aria-expanded={why}
              onClick={() => setWhy((value) => !value)}
              className="min-h-11 text-body inline-flex items-center justify-center rounded-full bg-sheet px-4 font-medium text-ink no-underline inset-ring-1 inset-ring-line-strong hover:bg-sunken"
            >
              Vì sao phần này?
            </button>
            {why && <p className="m-0 w-full rounded-control bg-sunken p-4 text-body">{suggestion.pace}</p>}
          </div>
        </>
      )}
    </Region>
  );
}

export function SessionScreen(props: SessionScreenProps) {
  const { subject, subjectId, stopHref, initial, api, footer } = props;
  // V11: a PDF, Word or PowerPoint file picked here goes to the subject's shared document store, so
  // it can be @-mentioned at once, even before the session is finished. The list grows with them.
  const [docs, setDocs] = useState(props.docs);
  const pieceMode = typeof api?.addPiece === "function";
  const [pieces, setPieces] = useState<Piece[]>([]);
  const [recording, setRecording] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [round, send] = useReducer(roundReducer, initial.round);
  const [text, setText] = useState(initial.text);
  const [mentions, setMentions] = useState(initial.mentions);
  // The upload callbacks outlive a render: they read the newest words and mentions from here.
  const latest = useRef({ text: initial.text, mentions: initial.mentions });
  useEffect(() => {
    latest.current = { text, mentions };
  }, [text, mentions]);
  const [files, setFiles] = useState(initial.files);
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [ended, setEnded] = useState(false);
  const counter = useRef(0);
  // T7.12c: what each uploaded row hands in, and the file itself for "Thử lại".
  const refs = useRef(new Map<string, FileRef>());
  const blobs = useRef(new Map<string, File>());
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

  // F2: the pieces kept so far come from core-api (a reopened page shows them again).
  useEffect(() => {
    if (!pieceMode || !api) return;
    void api.pieces().then((found) => {
      if (found.ok) setPieces(found.data.pieces);
    });
  }, [api, pieceMode]);

  async function record() {
    if (!api || recording || uploading > 0) return;
    if (text.trim() === "" && usableFiles === 0) {
      setProblem(SUBMIT_COPY.nothing);
      return;
    }
    setProblem(null);
    setRecording(true);
    const handed = new Map<string, FileRef>();
    for (const row of files) {
      const ref = row.state === "done" ? refs.current.get(row.id) : undefined;
      if (ref) handed.set(ref.sha256, ref);
    }
    const result = await api.addPiece(text, mentions, [...handed.values()]);
    setRecording(false);
    if (!result.ok) {
      setProblem(result.error === "text_too_long" ? SUBMIT_COPY.tooLong : SUBMIT_COPY.network);
      return;
    }
    setPieces((rows) => [...rows, result.data]);
    setText("");
    setMentions([]);
    setFiles([]);
    refs.current.clear();
    blobs.current.clear();
    say("Đã ghi lại một phần.");
  }

  async function dropPiece(id: string) {
    if (!api || completing) return;
    const result = await api.removePiece(id);
    if (result.ok) {
      setPieces((rows) => rows.filter((p) => p.id !== id));
      setProblem(null);
      say("Đã bỏ một phần.");
    } else {
      setProblem(completeProblem(result.status, result.error));
    }
  }

  async function complete() {
    if (!api || completing || pieces.length === 0) return;
    setCompleting(true);
    const result = await api.complete();
    if (!result.ok) {
      setCompleting(false);
      setProblem(completeProblem(result.status, result.error));
      return;
    }
    if (!subjectId || props.stayOnComplete) {
      // The preview has no subject page to go to: the same screen shows the reading and the cards.
      send({ type: "send" });
      return;
    }
    // SESSION-END: the session is in. The pop-up says well done and offers the way on; the "đã vào Kho"
    // toast comes by itself from the pending session.
    rememberPendingSession({ sessionId: api.sessionId, subjectId, subject });
    setEnded(true);
  }

  const uploading = files.filter((f) => f.state === "uploading").length;
  const usableFiles = files.filter((f) => f.state === "done").length;
  const suggestion = round.round > 1 ? props.nextSuggestion : props.suggestion;
  const isFree = props.suggestion.kind === "free" && round.round === 1;

  function finishRead() {
    send({ type: "done", result: props.readResult?.() ?? { cards: 0, title: null, notice: "no_content_found" } });
  }

  // T7.12: while the reading runs, ask core-api where it stands (never kept here, so leaving the
  // screen and coming back shows the true state). Done or failed ends the poll.
  useEffect(() => {
    if (!api || round.phase !== "processing" || round.submission === "failed") return;
    let stopped = false;
    const timer = window.setInterval(async () => {
      const found = await api.result();
      if (stopped || !found.ok) return;
      if (found.data.phase === "done") {
        const { cards, title, notice } = found.data;
        send({ type: "done", result: { cards, title, notice } });
      } else if (found.data.phase === "failed") send({ type: "failed" });
      else if (found.data.phase === "pending_ai") send({ type: "pending-ai" });
      else if (found.data.phase === "processing") send({ type: "processing" });
    }, POLL_MS);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [api, round.phase, round.submission]);

  function patchRow(id: string, patch: Partial<FileRow>) {
    setFiles((rows) => rows.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  }

  function startStoreUpload(subject: string, id: string, file: File) {
    patchRow(id, { state: "uploading", percent: 0 });
    void uploadPdf(subject, file, (state) => {
      if (state.kind === "uploading") patchRow(id, { state: "uploading", percent: state.percent });
      else if (state.kind === "done" && state.documentId) {
        const documentId = state.documentId;
        const name = file.name.replace(/\.[^.]+$/, "");
        const doc: DocRef = { id: documentId, name, role: "auxiliary" };
        // V11: the file is mentioned for the learner, so "Ghi lại" works with only a file.
        const next = appendMention(latest.current.text, doc, latest.current.mentions);
        latest.current = next;
        setText(next.text);
        setMentions(next.mentions);
        setDocs((rows) => (rows.some((d) => d.id === documentId) ? rows : [...rows, { id: documentId, name, role: "auxiliary" }]));
        patchRow(id, { state: "done" });
        say(`Đã tải ${name} vào kho tài liệu của môn và tham chiếu vào phần bạn đã học.`);
      } else if (state.kind === "failed") patchRow(id, { state: rowStateOf(state.code === "unsupported_file_type" ? "unsupported" : state.code) });
    });
  }

  function startUpload(id: string, file: File) {
    if (!api) return;
    if (subjectId && /\.(pdf|docx|pptx)$/i.test(file.name)) return startStoreUpload(subjectId, id, file);
    blobs.current.set(id, file);
    patchRow(id, { state: "uploading", percent: 0 });
    void api.upload(file, (state) => {
      if (state.kind === "uploading") patchRow(id, { state: "uploading", percent: state.percent });
      else if (state.kind === "ready") {
        refs.current.set(id, state.ref);
        patchRow(id, { state: "done" });
      } else patchRow(id, { state: rowStateOf(state.code) });
    });
  }

  function addFiles(added: File[]) {
    const rows = added.map((file) => ({ id: newId(), file }));
    setFiles((current) => [
      ...current,
      ...rows.map(({ id, file }) => ({ id, name: file.name, kind: kindOf(file.name), state: "uploading" as const, percent: 0 })),
    ]);
    for (const { id, file } of rows) startUpload(id, file);
  }

  function removeFile(id: string) {
    refs.current.delete(id);
    blobs.current.delete(id);
    setFiles((rows) => rows.filter((row) => row.id !== id));
  }

  async function handIn() {
    if (!api) return;
    // The same file twice is one (core-api keys a note by its hash).
    const handed = new Map<string, FileRef>();
    for (const row of files) {
      const ref = row.state === "done" ? refs.current.get(row.id) : undefined;
      if (ref) handed.set(ref.sha256, ref);
    }
    const result = await api.submit(text, mentions, [...handed.values()]);
    if (result.ok) {
      if (result.data.status !== "queued") send({ type: "processing" });
      return;
    }
    if (result.docId) {
      send({ type: "scope-rejected", docId: result.docId });
      say(SUBMIT_COPY.mention);
      return;
    }
    send({ type: "back" });
    setProblem(
      result.error === "text_too_long" ? SUBMIT_COPY.tooLong : result.error === "nothing_submitted" ? SUBMIT_COPY.nothing : SUBMIT_COPY.network,
    );
  }

  function submit() {
    if (uploading > 0) return;
    if (text.trim() === "" && usableFiles === 0) {
      setProblem(api ? SUBMIT_COPY.nothing : "Thêm ít nhất một file hoặc vài dòng mô tả.");
      return;
    }
    setProblem(null);
    setNote("");
    send({ type: "send" });
    if (api) {
      void handIn();
      return;
    }
    if (props.autoAdvance) {
      later(600, () => send({ type: "processing" }));
      later(1600, finishRead);
    }
  }

  /** "Thử lại": the same words go again; with none left (the page was reopened) the form shows. */
  function retry() {
    if (!api) {
      send({ type: "retry" });
      return;
    }
    if (text.trim() === "") {
      send({ type: "back" });
      return;
    }
    send({ type: "retry" });
    void handIn();
  }

  const exit =
    round.phase === "done" ? null : (
      <Link href={stopHref} className={buttonVariants({ variant: "quiet" })}>
        Dừng
      </Link>
    );

  return (
    <FocusShell position={0} total={0} exit={exit} title={<span title={subject}>{subject}</span>}>
      <div className="mx-auto flex w-full max-w-170 flex-col gap-10">
        <p className="sr-only" role="status" aria-live="polite">
          {note || round.announce}
        </p>
        {history.map((line) => (
          <DoneLine key={line} label={line} />
        ))}

        {round.phase === "compose" ? (
          <>
            <h1 className="m-0 font-display text-title">Buổi học mới</h1>
            <Suggest suggestion={isFree ? { kind: "free", text: "Buổi học tự do. Bài nộp không gắn phần đề cương." } : suggestion} id="suggest" />
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
                onAdd={
                  api
                    ? addFiles
                    : (added) =>
                        setFiles((rows) => [
                          ...rows,
                          ...added.map((file) => ({ id: newId(), name: file.name, kind: kindOf(file.name), state: "done" as const })),
                        ])
                }
                onRemove={removeFile}
                onRetry={(id) => {
                  const file = blobs.current.get(id);
                  if (api && file) startUpload(id, file);
                  else patchRow(id, { state: "done" });
                }}
              />
              <div className="sticky bottom-0 z-10 flex flex-col items-start gap-2 bg-bg py-3 max-[640px]:[&>button]:w-full min-[641px]:static min-[641px]:bg-transparent min-[641px]:py-0">
                <Button
                  type="button"
                  className="max-[480px]:w-full"
                  aria-disabled={uploading > 0 || undefined}
                  aria-describedby={uploading > 0 ? "session-send-why" : undefined}
                  onClick={pieceMode ? () => void record() : submit}
                >
                  {pieceMode ? (recording ? "Đang ghi…" : "Ghi lại") : "Gửi"}
                </Button>
                {uploading > 0 && (
                  <span id="session-send-why">
                    <FieldHint id="session-send-hint">Đang tải {uploading} file…</FieldHint>
                  </span>
                )}
              </div>
              {pieceMode && pieces.length > 0 && (
                <section aria-label="Đã học trong buổi" className="flex flex-col gap-3 border-t border-line pt-5">
                  <h3 className="m-0 font-display text-lead">Đã học trong buổi</h3>
                  <ol className="m-0 flex list-none flex-col gap-2 p-0">
                    {pieces.map((p, index) => (
                      <li key={p.id} className="rounded-control bg-sunken p-3 text-body wrap-anywhere">
                        <span className="flex items-center justify-between gap-2">
                          <span className="text-meta text-ink-soft">Phần {index + 1}</span>
                          <button
                            type="button"
                            aria-label={`Bỏ phần ${index + 1}`}
                            onClick={() => void dropPiece(p.id)}
                            className="inline-flex min-h-11 items-center justify-center rounded-full bg-sheet px-4 text-meta font-medium text-ink no-underline inset-ring-1 inset-ring-line-strong hover:bg-sunken"
                          >
                            Bỏ phần này
                          </button>
                        </span>
                        <p className="m-0 whitespace-pre-line">
                          {p.text || `${p.fileCount} file`}
                          {p.text && p.fileCount > 0 ? ` (+${p.fileCount} file)` : ""}
                        </p>
                      </li>
                    ))}
                  </ol>
                  <Button type="button" aria-disabled={completing || undefined} onClick={() => void complete()}>
                    {completing ? "Đang kết thúc…" : "Kết thúc buổi học"}
                  </Button>
                </section>
              )}
            </Region>
          </>
        ) : (
          <>
            <DoneLine label={isFree ? "Gợi ý: học tự do" : `Gợi ý: ${suggestion.kind === "section" ? suggestion.text : "học tự do"}`} />
            <DoneLine label={`Bài nộp: ${files.length} file, ${text.trim() ? 1 : 0} mô tả`}>
              {text.trim() ? <span className="whitespace-pre-line">{text}</span> : null}
            </DoneLine>
          </>
        )}

        {round.phase === "processing" && round.submission && (
          <Region phase="processing" title="Đang đọc bài nộp">
            <ProcessingArea submission={round.submission} onRetry={retry} />
          </Region>
        )}

        {round.phase === "done" && round.result && (
          <>
            <Region phase="done" title={round.result.cards > 0 ? "Đã thêm vào Kho" : "Chưa có thẻ mới"}>
              <DoneArea
                result={round.result}
                subjectId={subjectId}
                sessionId={api?.sessionId ?? ""}
                stopHref={stopHref}
                onContinue={() => {
                  setHistory((lines) => [
                    ...lines,
                    round.result && round.result.cards > 0 ? `Vòng ${round.round}: đã thêm ${round.result.cards} thẻ vào Kho` : `Vòng ${round.round}: chưa có thẻ mới`,
                  ]);
                  setText("");
                  setMentions([]);
                  setFiles([]);
                  refs.current.clear();
                  blobs.current.clear();
                  send({ type: "continue" });
                }}
              />
            </Region>
          </>
        )}
        {footer}
      </div>
      {subjectId && (
        <SessionEndDialog
          open={ended}
          onHome={() => window.location.assign("/today")}
          onMore={() => window.location.assign(`/subjects/${subjectId}/sessions/study`)}
        />
      )}
    </FocusShell>
  );
}
