"use client";

import { useState } from "react";

import { FieldError } from "@/components/field-error";
import { Button } from "@/components/ui/button";
import { ANSWER_MAX } from "@/lib/review-client";

// T2.15 (US-04, DESIGN.md §3.4, §6.4): writing on the page. Ruled lines 32px apart with the text
// sitting on them, upright pink; no box. An empty answer is stopped here (US-04 AC4), one over
// ai-service's 4000 characters too (plan 🟡15). The save line never shows an error (AC3).

export type SaveState = "idle" | "saving" | "saved" | "local";

export type AnswerBoxProps = {
  id: string;
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onForgot: () => void;
  save: { state: SaveState; at: number | null };
  /** Which button is waiting for core-api: nothing can be sent twice meanwhile. */
  pending: "submit" | "forgot" | null;
};

/** Shown from here on, so the limit never comes as a surprise. */
const COUNT_FROM = 3500;

const number = new Intl.NumberFormat("vi-VN");

/** "21:42" in the user's own clock. */
export function clock(at: number): string {
  return new Date(at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", hour12: false });
}

function SaveLine({ save }: Pick<AnswerBoxProps, "save">) {
  if (save.state === "saving") return <span>Đang lưu…</span>;
  if (save.state === "saved" && save.at !== null) return <span>Đã lưu nháp lúc {clock(save.at)}</span>;
  if (save.state === "local") return <span>Đã lưu trên máy này, sẽ đồng bộ khi có mạng</span>;
  return <span />;
}

export function AnswerBox({ id, value, onChange, onSubmit, onForgot, save, pending }: AnswerBoxProps) {
  const [empty, setEmpty] = useState(false);
  const tooLong = value.length > ANSWER_MAX;
  const busy = pending !== null;

  function send() {
    if (busy || tooLong) return;
    if (!value.trim()) {
      setEmpty(true);
      return;
    }
    onSubmit();
  }

  const problem = tooLong ? `${id}-long` : empty ? `${id}-empty` : undefined;
  return (
    <div>
      <label className="sr-only" htmlFor={id}>
        Câu trả lời của bạn
      </label>
      <textarea
        id={id}
        value={value}
        maxLength={ANSWER_MAX}
        placeholder="Viết câu trả lời của bạn"
        // Focus goes to the box when the question shows (DESIGN.md §6.4).
        autoFocus
        aria-invalid={problem ? true : undefined}
        aria-describedby={problem}
        onChange={(event) => {
          setEmpty(false);
          onChange(event.target.value);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            send();
          }
        }}
        className="mt-5 block field-sizing-content max-h-112 min-h-40 w-full resize-none rounded-none border-0 bg-transparent bg-[linear-gradient(transparent_31px,var(--line)_31px,var(--line)_32px)] bg-size-[100%_32px] [background-attachment:local] p-0 text-answer text-hong outline-none placeholder:text-ink-soft focus-visible:rounded-control focus-visible:outline-2 focus-visible:outline-offset-8 focus-visible:outline-focus aria-invalid:rounded-control aria-invalid:outline-2 aria-invalid:outline-offset-8 aria-invalid:outline-partial aria-invalid:outline-dashed"
      />
      <p className="m-0 mt-2.5 flex justify-between gap-3 text-meta text-ink-soft" aria-live="polite">
        <SaveLine save={save} />
        {value.length > COUNT_FROM ? (
          <span className="tabular-nums">
            {number.format(value.length)} / {number.format(ANSWER_MAX)}
          </span>
        ) : (
          <span className="max-[900px]:hidden">Ctrl+Enter để gửi</span>
        )}
      </p>
      {empty && (
        <div className="mt-2.5">
          <FieldError id={`${id}-empty`}>Ô trả lời đang trống. Nếu không nhớ, chọn Không nhớ.</FieldError>
        </div>
      )}
      {tooLong && (
        <div className="mt-2.5">
          <FieldError id={`${id}-long`}>
            <span data-copy="tam">Câu trả lời dài hơn 4.000 ký tự. Rút gọn bớt rồi gửi.</span>
          </FieldError>
        </div>
      )}
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Button type="button" pending={pending === "submit"} disabled={busy && pending !== "submit"} onClick={send}>
          Gửi
        </Button>
        <Button
          type="button"
          variant="quiet"
          pending={pending === "forgot"}
          disabled={busy && pending !== "forgot"}
          onClick={() => {
            if (!busy) onForgot();
          }}
        >
          Không nhớ
        </Button>
      </div>
    </div>
  );
}
