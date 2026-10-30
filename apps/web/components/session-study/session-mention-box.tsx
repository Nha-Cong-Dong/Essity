"use client";

import { useId, useLayoutEffect, useRef, useState } from "react";

import { FieldError } from "@/components/field-error";
import {
  activeMention,
  applyMention,
  type DocRef,
  filterDocs,
  type Mention,
  reconcileMentions,
} from "@/lib/session-study/mention";

// T7.12a (US-02 AC2-AC4; DESIGN.md §6.7 vùng 2; design decisions C2-C4, C14): the description on
// ruled lines. Typing `@` opens a list of the subject's documents (ARIA combobox on a plain
// textarea: the field keeps focus, ↑/↓ move, Enter chooses, Tab and Esc close). What follows the
// chosen name is resolved by the backend on submit, so a chip here is only the document.

export type MentionBoxProps = {
  value: string;
  mentions: Mention[];
  docs: DocRef[];
  onChange: (value: string, mentions: Mention[]) => void;
  /** Said to the polite live region ("Đã bỏ tham chiếu Giáo trình"). */
  say: (text: string) => void;
  /** Document whose part after @ the backend refused (shown on its chip). */
  rejectedDoc: string | null;
  /** A problem with the whole form ("Thêm ít nhất một file hoặc vài dòng mô tả."). */
  problem: string | null;
};

const PLACEHOLDER = "Tối nay mình học @Giáo trình mục 3.2 và xem lại @slide c3 tr. 10–14.";

export function MentionBox({ value, mentions, docs, onChange, say, rejectedDoc, problem }: MentionBoxProps) {
  const id = useId();
  const fieldRef = useRef<HTMLTextAreaElement>(null);
  const caretAfter = useRef<number | null>(null);
  const [caret, setCaret] = useState(0);
  const [dismissed, setDismissed] = useState<number | null>(null);
  const [active, setActive] = useState(0);
  const [above, setAbove] = useState(false);

  const found = activeMention(value, caret, mentions);
  const open = found !== null && found.at !== dismissed;
  const options = found ? filterDocs(docs, found.query) : [];
  const index = Math.min(active, Math.max(options.length - 1, 0));
  const listId = `${id}-list`;

  useLayoutEffect(() => {
    if (caretAfter.current !== null && fieldRef.current) {
      fieldRef.current.setSelectionRange(caretAfter.current, caretAfter.current);
      caretAfter.current = null;
    }
  });

  function place() {
    const field = fieldRef.current;
    if (!field) return;
    const rect = field.getBoundingClientRect();
    const viewport = window.visualViewport?.height ?? window.innerHeight;
    const below = viewport - rect.bottom;
    setAbove(below < 200 && rect.top > below);
  }

  function choose(doc: DocRef) {
    if (!found) return;
    const next = applyMention(value, found.at, caret, doc, mentions);
    caretAfter.current = next.caret;
    setCaret(next.caret);
    setDismissed(null);
    onChange(next.text, next.mentions);
    fieldRef.current?.focus();
  }

  function key(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (!open || !found) return;
    if (event.key === "Escape") {
      event.preventDefault();
      setDismissed(found.at);
    } else if (event.key === "Tab") {
      setDismissed(found.at);
    } else if (options.length > 0) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActive((index + 1) % options.length);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActive((index - 1 + options.length) % options.length);
      } else if (event.key === "Home" || event.key === "End") {
        event.preventDefault();
        setActive(event.key === "Home" ? 0 : options.length - 1);
      } else if (event.key === "Enter" && !event.nativeEvent.isComposing && event.keyCode !== 229) {
        event.preventDefault();
        choose(options[index]);
      }
    }
  }

  function change(event: React.ChangeEvent<HTMLTextAreaElement>) {
    const next = event.target.value;
    const { mentions: kept, removed } = reconcileMentions(value, next, mentions);
    if (removed.length > 0) say(`Đã bỏ tham chiếu ${removed.map((m) => m.name).join(", ")}`);
    setCaret(event.target.selectionStart);
    setActive(0);
    place();
    onChange(next, kept);
  }

  const describedBy = [problem ? `${id}-problem` : null, rejectedDoc ? `${id}-rejected` : null].filter(Boolean).join(" ");
  const rejected = mentions.find((m) => m.docId === rejectedDoc);
  const message = !open
    ? ""
    : options.length > 0
      ? `${options.length} tài liệu khớp`
      : docs.length === 0
        ? "Kho tài liệu của môn đang trống."
        : "Không có tài liệu tên này trong kho.";

  return (
    <div className="flex flex-col gap-3">
      <label className="sr-only" htmlFor={`${id}-field`}>
        Mô tả buổi học. Gõ @ để chọn tài liệu.
      </label>
      <div className="relative">
        <textarea
          ref={fieldRef}
          id={`${id}-field`}
          value={value}
          placeholder={PLACEHOLDER}
          role="combobox"
          aria-expanded={open}
          aria-controls={open ? listId : undefined}
          aria-autocomplete="list"
          aria-haspopup="listbox"
          aria-activedescendant={open && options.length > 0 ? `${id}-opt-${index}` : undefined}
          aria-invalid={problem || rejectedDoc ? true : undefined}
          aria-describedby={describedBy || undefined}
          onChange={change}
          onKeyDown={key}
          onSelect={(event) => {
            setCaret(event.currentTarget.selectionStart);
            setDismissed(null);
          }}
          className="block field-sizing-content max-h-112 min-h-40 w-full resize-none rounded-none border-0 bg-transparent bg-[linear-gradient(transparent_31px,var(--line)_31px,var(--line)_32px)] bg-size-[100%_32px] [background-attachment:local] p-0 text-answer text-hong outline-none placeholder:text-ink-soft focus-visible:rounded-control focus-visible:outline-2 focus-visible:outline-offset-8 focus-visible:outline-focus aria-invalid:rounded-control aria-invalid:outline-2 aria-invalid:outline-offset-8 aria-invalid:outline-partial aria-invalid:outline-dashed"
        />
        {open && (
          <ul
            id={listId}
            role="listbox"
            aria-label="Tài liệu trong kho"
            className={`absolute right-0 left-0 z-20 m-0 max-h-[min(40svh,18rem)] list-none overflow-y-auto rounded-sheet bg-raised p-1 shadow-over ${above ? "bottom-full mb-3" : "top-full mt-3"}`}
          >
            {options.length === 0 ? (
              <li role="presentation" className="p-3 text-body text-ink-soft">
                {docs.length === 0
                  ? "Kho tài liệu của môn đang trống. Tải tài liệu lên bằng vùng thả file."
                  : "Không có tài liệu tên này trong kho."}
              </li>
            ) : (
              options.map((doc, i) => (
                <li
                  key={doc.id}
                  id={`${id}-opt-${i}`}
                  role="option"
                  aria-selected={i === index}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => choose(doc)}
                  className={`flex min-h-12 cursor-pointer flex-col justify-center rounded-control px-3 py-1.5 ${i === index ? "bg-sunken" : ""}`}
                >
                  <span className="truncate text-body">{doc.name}</span>
                  <span className="truncate text-meta text-ink-soft">{doc.role}</span>
                </li>
              ))
            )}
          </ul>
        )}
      </div>
      <p className="sr-only" role="status" aria-live="polite">
        {message}
      </p>
      {mentions.length > 0 && (
        <ul className="m-0 flex list-none flex-wrap gap-2 p-0" aria-label="Tài liệu đã chọn">
          {mentions.map((m) => (
            <li
              key={`${m.docId}-${m.start}`}
              className={`flex min-h-10 max-w-full items-center gap-2 rounded-full px-4 text-meta text-ink ${
                m.docId === rejectedDoc ? "border-2 border-partial bg-sunken" : "bg-rose-100"
              }`}
            >
              <span className="truncate">{m.name}</span>
              <button
                type="button"
                aria-label={`Bỏ tham chiếu ${m.name}`}
                onClick={() => onChange(value, mentions.filter((x) => x !== m))}
                className="grid size-6 shrink-0 place-items-center rounded-full text-ink-soft hover:text-ink"
              >
                <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
                  <path d="M1.5 1.5 8.5 8.5M8.5 1.5 1.5 8.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
              </button>
            </li>
          ))}
        </ul>
      )}
      {rejected && (
        <FieldError id={`${id}-rejected`}>
          Chưa rõ phần sau {rejected.name}. Thử viết &quot;mục 3.2&quot; hoặc &quot;tr. 40–55&quot;; câu của bạn vẫn được giữ.
        </FieldError>
      )}
      {problem && <FieldError id={`${id}-problem`}>{problem}</FieldError>}
    </div>
  );
}
