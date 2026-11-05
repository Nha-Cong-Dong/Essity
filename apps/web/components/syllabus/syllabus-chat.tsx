"use client";

import { type FormEvent, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

// E3: the chat at the foot of the syllabus-customise screen. The learner writes what bothers them in
// plain Vietnamese; core-api answers with a short Vietnamese sentence, shown under the input.

/** The outline on screen reads itself again when the chat changed it. */
export const SYLLABUS_CHANGED = "essity:syllabus-changed";

const EXAMPLES = ["gộp phần 1.2 với 1.3", "bỏ phần phụ lục", "tách chương 3"];
const OFFLINE = "Chưa gửi được. Bạn kiểm tra kết nối rồi thử lại nhé.";

type Answer = { tone: "ok" | "info"; text: string; undoId?: string };

export function OutlineChat({ subjectId, onChanged }: { subjectId: string; onChanged: () => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const input = useRef<HTMLInputElement>(null);

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const words = text.trim();
    if (busy || words === "") return;
    setBusy(true);
    setAnswer(null);
    try {
      const response = await fetch(`/api/subjects/${subjectId}/outline/chat`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text: words }),
      });
      if (response.status === 401) {
        window.location.assign("/login");
        return;
      }
      const data = (await response.json().catch(() => null)) as {
        status?: string;
        reply?: string;
        command_id?: string | null;
      } | null;
      if (!response.ok || !data?.reply) {
        setAnswer({ tone: "info", text: OFFLINE });
        return;
      }
      if (data.status === "applied") {
        setText("");
        setAnswer({ tone: "ok", text: data.reply, undoId: data.command_id ?? undefined });
        window.dispatchEvent(new Event(SYLLABUS_CHANGED));
        onChanged();
      } else {
        setAnswer({ tone: "info", text: data.reply });
      }
    } catch {
      setAnswer({ tone: "info", text: OFFLINE });
    } finally {
      setBusy(false);
      input.current?.focus();
    }
  }

  // The reply says "Bấm Hoàn tác nếu bạn đổi ý": the button it names is here (QA 05/11).
  async function undo() {
    const id = answer?.undoId;
    if (!id || busy) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/commands/${id}/undo`, { method: "POST" });
      if (response.status === 401) {
        window.location.assign("/login");
        return;
      }
      if (response.ok) {
        setAnswer({ tone: "ok", text: "Đã hoàn tác." });
        window.dispatchEvent(new Event(SYLLABUS_CHANGED));
        onChanged();
      } else {
        setAnswer({ tone: "info", text: "Không hoàn tác được. Bạn thử lại hoặc sửa tay trong đề cương." });
      }
    } catch {
      setAnswer({ tone: "info", text: OFFLINE });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-syllabus-chat className="flex flex-col gap-3">
      <form method="post" onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <label htmlFor="chat-input" className="sr-only">
          Nói điều bạn muốn sửa trong đề cương
        </label>
        <Input
          id="chat-input"
          ref={input}
          value={text}
          maxLength={500}
          autoComplete="off"
          placeholder="Ví dụ: gộp phần 1.2 với 1.3"
          onChange={(e) => setText(e.target.value)}
          className="min-w-0 flex-1"
        />
        <Button type="submit" pending={busy} className="max-sm:w-full">
          {busy ? "Đang hiểu…" : "Gửi"}
        </Button>
      </form>
      <div role="status" aria-live="polite" data-chat-reply>
        {answer && <p className="m-0 text-body wrap-anywhere">{answer.text}</p>}
        {answer?.undoId && (
          <Button type="button" variant="quiet" onClick={() => void undo()} className="self-start">
            Hoàn tác
          </Button>
        )}
      </div>
      <p className="m-0 flex flex-wrap items-center gap-2 text-meta text-ink-soft">
        <span>Thử nói:</span>
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => {
              setText(example);
              input.current?.focus();
            }}
            className="min-h-11 rounded-control border border-line-strong px-3 text-meta"
          >
            {example}
          </button>
        ))}
      </p>
    </div>
  );
}
