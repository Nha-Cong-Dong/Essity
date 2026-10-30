"use client";

import Link from "next/link";
import { type FormEvent, type KeyboardEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";

import { CommandDiff } from "@/components/command-diff";
import { COMMAND_MAX, type Diff, linkFor, normalizeCommand, summarize, tooLong } from "@/components/command/logic";
import type { Command, Outcome, Tray, UnclearReason, UndoOutcome } from "@/components/command/types";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// T9.3a (US-18 AC1, AC3, AC4, AC5, AC8; DESIGN §6.14; design-decisions.md in .work/T9.3a): the
// command bar and its tray, driven by `run` and `undo` props (no API yet). One result at a time
// (the newest); the undo stack is only the applied, not-undone commands, newest last. No primary
// button here: the screen keeps its own. No keyboard shortcut in M9 (decision C1).

export const TIMEOUT_MS = 20_000;
const FULL = "max-sm:w-full";

const COPY = {
  label: "Gõ một lệnh để sửa",
  send: "Gửi",
  understanding: "Đang hiểu lệnh…",
  done: "Đã làm:",
  undone: "Đã hoàn tác:",
  undo: "Hoàn tác",
  undoPrevious: "Hoàn tác lệnh trước",
  previous: "Lệnh trước đó:",
  latest: "Lệnh gần nhất:",
  retry: "Thử lại",
  notAllowed: "Thao tác này không làm bằng lệnh.",
  tooLong: `Lệnh dài quá. Rút gọn còn tối đa ${COMMAND_MAX} ký tự.`,
  exhausted: "Thanh lệnh tạm tắt vì hết lượt AI. Bạn vẫn sửa trực tiếp được.",
  errorCertain: "Không chạy được lệnh. Chưa có gì thay đổi.",
  errorUnsure: "Chưa chắc lệnh đã chạy. Bấm Thử lại, hệ thống sẽ không làm hai lần.",
  undoFailed: "Không hoàn tác được:",
  undoUnsure: "chưa chắc lệnh đã được hoàn tác, thử lại sau",
};

const UNCLEAR: Record<Exclude<UnclearReason, "unsupported">, string> = {
  ambiguous: "Chưa rõ: lệnh này hiểu được theo hơn một cách. Nói rõ mục hoặc thẻ nào.",
  unknown_target: "Chưa rõ: không thấy mục hay thẻ đó ở màn này.",
  missing_info: "Chưa rõ: còn thiếu một thông tin, ví dụ số trang hoặc ngày.",
};

const LINK_LABEL: Record<string, string> = { card: "Xem thẻ", section: "Xem mục", question: "Xem câu" };

// The rule of the tray (decision O1): when line 1 is neither done nor undone and a command can
// still be undone, the newest one is named beside its Hoàn tác button.
const NAMES_LATEST: Tray["kind"][] = ["unclear", "not-allowed", "too-long", "error", "pending-ai"];

type Focus = "input" | "tray" | "retry";

export type CommandBarProps = {
  /** A command that fits what the screen shows, e.g. "mục 3.4 kết thúc ở trang 80". Required. */
  example: string;
  run: (command: Command, signal: AbortSignal) => Promise<Outcome>;
  undo: (signal: AbortSignal) => Promise<UndoOutcome>;
  /** The first tray and undo stack (a fixture, or a screen that restores them). */
  initial?: { tray?: Tray; stack?: Diff[]; text?: string };
  /** Replaces the sentence for "hết lượt AI" on a screen with commands that have no manual path. */
  exhaustedNote?: string;
};

const coarse = (): boolean => window.matchMedia?.("(pointer: coarse)").matches === true;

export function CommandBar({ example, run, undo, initial, exhaustedNote }: CommandBarProps) {
  const [text, setText] = useState(initial?.text ?? "");
  const [tray, setTray] = useState<Tray>(initial?.tray ?? { kind: "idle" });
  const [stack, setStack] = useState<Diff[]>(initial?.stack ?? []);
  const [focus, setFocus] = useState<{ to: Focus; n: number } | null>(null);
  const busy = tray.kind === "understanding";
  const quota = tray.kind === "pending-ai";
  // Kept after an error so that a resend of the same words reuses the id (core applies it once).
  const retry = useRef<Command | null>(null);
  const inFlight = useRef(false);
  const input = useRef<HTMLInputElement>(null);
  const trayBox = useRef<HTMLDivElement>(null);
  const retryButton = useRef<HTMLButtonElement>(null);
  const base = useId();
  const ids = { input: `${base}-in`, tray: `${base}-tray`, line: `${base}-line`, latest: `${base}-latest` };

  useEffect(() => {
    if (focus === null) return;
    const target = focus.to === "retry" ? retryButton.current : focus.to === "input" ? input.current : trayBox.current;
    target?.focus();
    target?.scrollIntoView?.({ block: "nearest" });
  }, [focus]);

  const settle = (to: Focus) => setFocus((f) => ({ to, n: (f?.n ?? 0) + 1 }));
  // Where a vanished button leaves focus: the input for a pointer (the keyboard stays), the tray
  // for a touch screen (no virtual keyboard popping up, and not lost on <body>).
  const settleAfterButton = () => settle(coarse() ? "tray" : "input");

  async function guarded<T>(call: (signal: AbortSignal) => Promise<T>): Promise<T | "timeout"> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    try {
      return await Promise.race([
        call(controller.signal),
        new Promise<"timeout">((resolve) => controller.signal.addEventListener("abort", () => resolve("timeout"))),
      ]);
    } catch {
      return "timeout";
    } finally {
      clearTimeout(timer);
    }
  }

  async function send(command: Command) {
    inFlight.current = true;
    setTray({ kind: "understanding" });
    const outcome = await guarded((signal) => run(command, signal));
    inFlight.current = false;
    if (outcome === "timeout" || outcome.kind === "error") {
      retry.current = command;
      setTray({ kind: "error", certain: outcome !== "timeout" && outcome.certain });
      settle(coarse() ? "tray" : "retry");
      return;
    }
    retry.current = null;
    if (outcome.kind === "done") {
      setStack((s) => [...s, outcome.diff]);
      setText("");
      setTray({ kind: "done", diff: outcome.diff });
    } else if (outcome.kind === "pending-ai") {
      setTray({ kind: "pending-ai" });
      settle(coarse() ? "tray" : "input");
    } else {
      setTray(outcome.kind === "unclear" ? { kind: "unclear", reason: outcome.reason } : { kind: "not-allowed" });
    }
  }

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (inFlight.current || busy || quota) return;
    const words = normalizeCommand(text);
    if (words === "") return settle("input");
    if (tooLong(words)) {
      setTray({ kind: "too-long" });
      return settle("input");
    }
    // Same words after a failure: the same command, not a second one.
    const again = retry.current !== null && retry.current.text === words;
    void send(again && retry.current !== null ? retry.current : { id: crypto.randomUUID(), text: words });
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    // An IME confirming a syllable sends Enter too (keyCode 229); it must not send the command.
    if (event.key === "Enter" && (event.nativeEvent.isComposing || event.keyCode === 229)) event.preventDefault();
  }

  async function undoLatest() {
    const last = stack.at(-1);
    if (inFlight.current || last === undefined) return;
    inFlight.current = true;
    const outcome = await guarded((signal) => undo(signal));
    inFlight.current = false;
    if (outcome === "timeout") {
      setTray({ kind: "undo-failed", reason: COPY.undoUnsure });
    } else if (outcome.kind === "undone") {
      setStack((s) => s.slice(0, -1));
      setTray({ kind: "undone", diff: last });
    } else {
      setTray({ kind: "undo-failed", reason: outcome.reason, ref: outcome.ref });
    }
    settleAfterButton();
  }

  const latest = stack.at(-1);
  const showLatest = latest !== undefined && NAMES_LATEST.includes(tray.kind);

  const undoButton = (label: string, describedBy: string) => (
    <Button type="button" variant="quiet" aria-describedby={describedBy} onClick={() => void undoLatest()}>
      {label}
    </Button>
  );
  const metaRow = (lead: string, label: string) =>
    latest === undefined ? null : (
      <div className="flex flex-wrap items-center justify-between gap-x-4 border-t border-line pt-1">
        <p id={ids.latest} className="min-w-0 flex-1 basis-60 text-meta text-ink-soft [overflow-wrap:anywhere]">
          {lead} <span data-user>{summarize(latest)}</span>
        </p>
        {undoButton(label, ids.latest)}
      </div>
    );

  let line: ReactNode = null;
  let action: ReactNode = null;
  switch (tray.kind) {
    case "understanding":
      line = <p className="text-body text-ink">{COPY.understanding}</p>;
      break;
    case "done":
      line = <CommandDiff lead={COPY.done} diff={tray.diff} id={ids.line} />;
      action = undoButton(COPY.undo, ids.line);
      break;
    case "undone":
      line = <CommandDiff lead={COPY.undone} diff={tray.diff} />;
      break;
    case "undo-failed":
      line = (
        <p className="text-body text-ink [overflow-wrap:anywhere]">
          {COPY.undoFailed} <span data-user>{tray.reason}</span>.
        </p>
      );
      break;
    case "unclear":
      line = <p className="text-body text-ink">{tray.reason === "unsupported" ? COPY.notAllowed : UNCLEAR[tray.reason]}</p>;
      break;
    case "not-allowed":
      line = <p className="text-body text-ink">{COPY.notAllowed}</p>;
      break;
    case "too-long":
      line = <p className="text-body text-ink">{COPY.tooLong}</p>;
      break;
    case "pending-ai":
      line = (
        <p id={ids.line} className="text-body text-ink">
          {exhaustedNote ?? COPY.exhausted}
        </p>
      );
      break;
    case "error":
      line = (
        <p id={ids.line} className="text-body text-ink">
          {tray.certain ? COPY.errorCertain : COPY.errorUnsure}
        </p>
      );
      action = (
        <Button ref={retryButton} type="button" variant="quiet" aria-describedby={ids.line} onClick={() => submit()}>
          {COPY.retry}
        </Button>
      );
      break;
    case "idle":
      break;
  }
  const ref = tray.kind === "undo-failed" ? tray.ref : undefined;
  const link = ref ? linkFor(ref) : null;

  return (
    <form method="post" aria-label="Thanh lệnh" onSubmit={submit} className="mt-4 mb-6" data-command-bar>
      <Label htmlFor={ids.input} className="sr-only">
        {COPY.label}
      </Label>
      <div className="flex items-start gap-3">
        <Input
          id={ids.input}
          ref={input}
          type="text"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={`Thử: ${example}`}
          enterKeyHint="send"
          autoComplete="off"
          autoCorrect="off"
          spellCheck={false}
          readOnly={busy || quota}
          aria-disabled={quota || undefined}
          aria-busy={busy || undefined}
          aria-describedby={quota ? ids.line : undefined}
          className="aria-disabled:bg-sunken aria-disabled:text-ink-soft"
        />
        <Button type="submit" variant="secondary" pending={busy} disabled={quota}>
          {COPY.send}
        </Button>
      </div>
      <div ref={trayBox} id={ids.tray} role="status" aria-live="polite" tabIndex={-1} data-tray className="outline-none">
        {tray.kind === "idle" ? null : (
          <div className="mt-3 flex flex-col gap-1 rounded-control bg-sunken px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
              <div className="min-w-0 flex-1 basis-60">{line}</div>
              {action ? <div className={FULL}>{action}</div> : null}
            </div>
            {showLatest ? metaRow(COPY.latest, COPY.undo) : null}
            {tray.kind === "undone" ? metaRow(COPY.previous, COPY.undoPrevious) : null}
            {link && ref ? (
              <Link href={link} className={buttonVariants({ variant: "quiet" })}>
                {LINK_LABEL[ref.kind]}
              </Link>
            ) : null}
          </div>
        )}
      </div>
    </form>
  );
}
