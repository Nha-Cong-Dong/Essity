"use client";

import { useRef, useState } from "react";

import { ConfirmCard } from "@/components/confirm-card";
import { FieldError } from "@/components/field-error";
import { Marker } from "@/components/notebook";
import { Button } from "@/components/ui/button";
import {
  type Card,
  cardToRanges,
  checkRange,
  type ConfirmRange,
  confirmSession,
  DESCRIPTION_MAX,
  describeSession,
  type RangeDraft,
  rowsToRanges,
  startingRows,
} from "@/lib/log-session";
import { logMessage } from "@/lib/log-session-copy";
import { go } from "@/lib/navigate";
import { NoteDrop, NoteList, useNotes } from "@/components/note-drop";

// T4.13a (US-02 AC1, AC4, AC5, AC11; DESIGN.md §6.10; screens-html log-session.html): three steps
// on one page. Tell it in a sentence, read the card, press Lưu. A sentence that could not be read
// (or took over the budget) leaves the page-range form to fill by hand; the sentence is kept.

type Phase =
  | { kind: "tell" }
  | { kind: "reading" }
  | { kind: "card"; card: Card }
  | { kind: "ask"; card: Card }
  | { kind: "form"; card: Card; rows: RangeDraft[] }
  | { kind: "saved" };

// What a failed save says besides "chưa lưu được": the limit hit, or the file that is wrong.
const SAVE_CODES = new Set([
  "rate_limited",
  "upload_incomplete",
  "content_mismatch",
  "size_mismatch",
  "bad_note",
]);

const FIELD =
  "h-13 w-full min-w-0 rounded-control border border-line-strong bg-sheet px-4 font-sans text-body text-ink outline-none hover:border-ink-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus aria-invalid:border-2 aria-invalid:border-partial";
const LABEL = "text-small font-semibold text-ink";

function Said({ text }: { text: string }) {
  return <p className="m-0 mt-5 text-answer whitespace-pre-wrap text-hong wrap-anywhere">{text}</p>;
}

function Problem({ code }: { code: string }) {
  return (
    <div role="alert" className="mt-3">
      <FieldError id="log-problem">
        <span data-copy="tam">{logMessage(code)}</span>
      </FieldError>
    </div>
  );
}

function RangeForm({
  card,
  rows,
  saving,
  waiting,
  failure,
  onRows,
  onSave,
}: {
  card: Card;
  rows: RangeDraft[];
  saving: boolean;
  waiting: boolean;
  failure: string | null;
  onRows: (rows: RangeDraft[]) => void;
  onSave: () => void;
}) {
  const [checked, setChecked] = useState(false);
  const problems = rows.map((row) => checkRange(row, card.documents));
  const change = (index: number, patch: Partial<RangeDraft>) =>
    onRows(rows.map((row, at) => (at === index ? { ...row, ...patch } : row)));

  return (
    <form
      method="post"
      noValidate
      className="mt-4"
      onSubmit={(event) => {
        event.preventDefault();
        setChecked(true);
        if (problems.every((problem) => problem === null)) onSave();
      }}
    >
      {rows.map((row, index) => {
        const problem = checked ? problems[index] : null;
        const errorId = `range-${index}-error`;
        return (
          <div key={index} className="mt-4 grid gap-4 first:mt-0 sm:grid-cols-[2fr_1fr_1fr]">
            <div className="flex flex-col gap-2">
              <label className={LABEL} htmlFor={`range-${index}-doc`}>
                Tài liệu
              </label>
              <select
                id={`range-${index}-doc`}
                className={FIELD}
                value={row.documentId}
                aria-invalid={problem === "document" ? true : undefined}
                aria-describedby={problem === "document" ? errorId : undefined}
                onChange={(event) => change(index, { documentId: event.target.value })}
              >
                {card.documents.map((doc) => (
                  <option key={doc.document_id} value={doc.document_id}>
                    {doc.short_name}
                  </option>
                ))}
              </select>
            </div>
            {(["from", "to"] as const).map((side) => (
              <div key={side} className="flex flex-col gap-2">
                <label className={LABEL} htmlFor={`range-${index}-${side}`}>
                  {side === "from" ? "Trang từ" : "Trang đến"}
                </label>
                <input
                  id={`range-${index}-${side}`}
                  className={FIELD}
                  type="text"
                  inputMode="numeric"
                  autoComplete="off"
                  value={row[side]}
                  aria-invalid={problem && problem !== "document" ? true : undefined}
                  aria-describedby={problem && problem !== "document" ? errorId : undefined}
                  onChange={(event) => change(index, { [side]: event.target.value })}
                />
              </div>
            ))}
            {problem && (
              <div role="alert" className="sm:col-span-3">
                <FieldError id={errorId}>
                  <span data-copy="tam">{logMessage(problem)}</span>
                </FieldError>
              </div>
            )}
          </div>
        );
      })}
      {failure && <Problem code={failure} />}
      <div className="mt-6">
        <Button type="submit" pending={saving} disabled={waiting}>
          Lưu
        </Button>
      </div>
    </form>
  );
}

function Ask({ card, onPick }: { card: Card; onPick: (documentId: string) => void }) {
  const candidates = card.candidate_document_ids.length
    ? card.documents.filter((doc) => card.candidate_document_ids.includes(doc.document_id))
    : card.documents;
  return (
    <section aria-labelledby="ask-lead" className="mt-6">
      <p id="ask-lead" className="m-0 font-hand text-lead text-pencil" data-copy="tam">
        hỏi lại một câu
      </p>
      <p className="m-0 mt-2 text-question">{card.question}</p>
      <div className="mt-4 flex flex-wrap gap-3">
        {candidates.map((doc) => (
          <Button key={doc.document_id} type="button" variant="secondary" onClick={() => onPick(doc.document_id)}>
            {doc.short_name}
          </Button>
        ))}
      </div>
    </section>
  );
}

export function LogSession({ subjectId, subjectName }: { subjectId: string; subjectName: string }) {
  const [text, setText] = useState("");
  const [phase, setPhase] = useState<Phase>({ kind: "tell" });
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);
  const notes = useNotes();

  function enter(card: Card) {
    notes.begin(card.session_id); // the draft exists: the files chosen go to storage
    if (card.card === "clarify") return setPhase({ kind: "ask", card });
    if (card.card === "manual") return setPhase({ kind: "form", card, rows: startingRows(card) });
    setPhase({ kind: "card", card });
  }

  async function send() {
    if (phase.kind === "reading") return;
    if (!text.trim()) return setProblem("empty");
    setProblem(null);
    setPhase({ kind: "reading" });
    const result = await describeSession(subjectId, text);
    if (result.ok) return enter(result.data);
    if (result.code === "signed_out") return go("/login");
    setPhase({ kind: "tell" });
    setProblem(result.code);
  }

  async function save(card: Card, ranges: ConfirmRange[]) {
    if (saving) return;
    setSaving(true);
    setProblem(null);
    const result = await confirmSession(card.session_id, ranges, card.studied_on, notes.notes);
    setSaving(false);
    if (result.ok) return setPhase({ kind: "saved" });
    if (result.code === "signed_out") return go("/login");
    setProblem(SAVE_CODES.has(result.code) ? result.code : "save_failed");
  }

  function editSentence() {
    setProblem(null);
    setPhase({ kind: "tell" });
    // The sentence stays in the box: one correction, not a retype.
    setTimeout(() => box.current?.focus(), 0);
  }

  const telling = phase.kind === "tell" || phase.kind === "reading";
  return (
    <>
      <p className="m-0 text-meta text-ink-soft">{subjectName}</p>
      <h1 id="log-title" className="m-0 mt-1.5 font-display text-title">
        <Marker>Hôm nay bạn học gì?</Marker>
      </h1>
      {telling ? (
        <div className="mt-6">
          {phase.kind === "tell" ? (
            <>
              <label className="sr-only" htmlFor="said">
                Kể lại buổi học
              </label>
              <textarea
                id="said"
                ref={box}
                value={text}
                maxLength={DESCRIPTION_MAX}
                autoFocus
                placeholder="Ví dụ: tối nay học tiếp giáo trình Vật lý, hết phần tán xạ ánh sáng."
                aria-invalid={problem ? true : undefined}
                aria-describedby={problem ? "log-problem" : undefined}
                onChange={(event) => {
                  setProblem(null);
                  setText(event.target.value);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                    event.preventDefault();
                    void send();
                  }
                }}
                className="block field-sizing-content max-h-112 min-h-32 w-full resize-none rounded-none border-0 bg-transparent bg-[linear-gradient(transparent_31px,var(--line)_31px,var(--line)_32px)] bg-size-[100%_32px] [background-attachment:local] p-0 text-answer text-hong outline-none placeholder:text-ink-soft focus-visible:rounded-control focus-visible:outline-2 focus-visible:outline-offset-8 focus-visible:outline-focus aria-invalid:rounded-control aria-invalid:outline-2 aria-invalid:outline-offset-8 aria-invalid:outline-partial aria-invalid:outline-dashed"
              />
              {problem && <Problem code={problem} />}
              <NoteDrop onAdd={notes.add} />
              <NoteList rows={notes.rows} onRemove={notes.remove} />
              <div className="mt-6">
                <Button type="button" onClick={() => void send()}>
                  Gửi
                </Button>
              </div>
            </>
          ) : (
            <>
              <Said text={text} />
              <p className="m-0 mt-6 font-hand text-lead text-pencil" role="status">
                Đang đọc câu của bạn…
              </p>
              <div className="mt-4 flex flex-col gap-3" aria-hidden="true">
                <span className="h-7 w-2/5 rounded-control bg-sunken" />
                <span className="h-5 w-7/10 rounded-control bg-sunken" />
                <span className="h-20 rounded-control bg-sunken" />
              </div>
            </>
          )}
        </div>
      ) : (
        <>
          <Said text={text} />
          {phase.kind !== "saved" && <NoteList rows={notes.rows} onRemove={notes.remove} />}
          {phase.kind === "card" && (
            <>
              <ConfirmCard
                card={phase.card}
                saving={saving}
                waiting={notes.busy}
                onSave={() => void save(phase.card, cardToRanges(phase.card))}
                onSentence={editSentence}
                onRanges={() => setPhase({ kind: "form", card: phase.card, rows: startingRows(phase.card) })}
              />
              {problem && <Problem code={problem} />}
            </>
          )}
          {phase.kind === "ask" && (
            <Ask
              card={phase.card}
              onPick={(id) => setPhase({ kind: "form", card: phase.card, rows: startingRows(phase.card, id) })}
            />
          )}
          {phase.kind === "form" && (
            <section aria-labelledby="form-lead" className="mt-6">
              <p id="form-lead" className="m-0 font-hand text-lead text-pencil">
                chọn giúp app khoảng trang
              </p>
              {phase.card.documents.length === 0 ? (
                <p className="m-0 mt-2" data-copy="tam">
                  Môn này chưa có tài liệu nào đọc xong để chọn trang.
                </p>
              ) : (
                <>
                  <p className="m-0 mt-2">Chưa đọc được khoảng trang từ câu trên. Câu của bạn vẫn được giữ.</p>
                  <RangeForm
                    card={phase.card}
                    rows={phase.rows}
                    saving={saving}
                    waiting={notes.busy}
                    failure={problem}
                    onRows={(rows) => setPhase({ kind: "form", card: phase.card, rows })}
                    onSave={() => void save(phase.card, rowsToRanges(phase.rows))}
                  />
                </>
              )}
            </section>
          )}
          {phase.kind === "saved" && (
            <section aria-label="Đã lưu" className="mt-6" role="status">
              <p className="m-0 text-read" data-copy="tam">
                Đã lưu buổi học. Câu hỏi sẽ được soạn từ những trang này.
              </p>
              <div className="mt-6">
                <Button render={<a href="/today" />} nativeButton={false}>
                  Hôm nay
                </Button>
              </div>
            </section>
          )}
        </>
      )}
    </>
  );
}
