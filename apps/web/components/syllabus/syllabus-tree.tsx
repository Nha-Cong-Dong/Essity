"use client";

import { type KeyboardEvent, type ReactNode, useEffect, useId, useRef, useState } from "react";

import { FieldError } from "@/components/field-error";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  applyMark,
  applyRange,
  countCountable,
  defaultOpen,
  describeNode,
  excludeToggle,
  findNode,
  markCounts,
  nodeStatus,
  rangeContext,
  rangeText,
  type Row,
  type SyllabusNode,
  type Unit,
  validateRange,
  visibleRows,
} from "@/lib/syllabus/tree";

// T7.5a (US-13 AC4-AC6; DESIGN §6.6; design-decisions.md R1-R2): the outline as an ARIA tree with
// one tab stop (roving tabindex). Arrow keys move and fold; Enter on a branch folds it, on a leaf it
// opens that row's action panel and moves focus into it; the real ⋯ button opens the panel for a
// branch (and for touch). No dialogs: every action has its opposite button. Only the learner's own
// action moves focus; anything else goes to the status line.

export type PanelState = {
  id: string;
  mode: "actions" | "edit";
  from?: string;
  to?: string;
  /** Show the range error from the start (static preview state). */
  error?: boolean;
  saveError?: boolean;
  /** Move focus into the panel when it mounts (true for the learner's own action). */
  focus?: boolean;
};

type Props = {
  label: string;
  nodes: SyllabusNode[];
  unit: Unit;
  total: number;
  onNodes: (nodes: SyllabusNode[]) => void;
  say: (text: string) => void;
  onEditing: (editing: boolean) => void;
  initialPanel?: PanelState | null;
};

// Indent: 28 px a level from 640 px, 16 px below; the real indent stops at level 4 / 3 so a deep
// outline keeps room for its titles at 320 px. aria-level stays true.
const INDENT =
  "pl-[calc(min(var(--lvl),var(--cap))*var(--step))] [--lvl:0] [--cap:3] [--step:16px] sm:[--cap:4] sm:[--step:28px]";
// The visible mark is 28 px; its touch area is 44 px (after:) without widening the indent step.
const HIT = "relative after:absolute after:-inset-2 after:content-['']";

function Tick() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" className="text-correct">
      <path d="m3 8.5 3.2 3.2L13 4.8" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Half() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" className="text-ink">
      <circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8 2a6 6 0 0 1 0 12z" fill="currentColor" />
    </svg>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width="16"
      height="16"
      aria-hidden="true"
      className={`transition-transform duration-(--dur-ui) motion-reduce:transition-none ${open ? "rotate-90" : ""}`}
    >
      <path d="m6 3 5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Dots() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      {[3, 8, 13].map((x) => (
        <circle key={x} cx={x} cy="8" r="1.5" fill="currentColor" />
      ))}
    </svg>
  );
}

function Panel({
  node,
  unit,
  nodes,
  total,
  state,
  setState,
  onNodes,
  say,
  focusRow,
  level,
}: {
  node: SyllabusNode;
  unit: Unit;
  nodes: SyllabusNode[];
  total: number;
  state: PanelState;
  setState: (next: PanelState | null) => void;
  onNodes: (nodes: SyllabusNode[]) => void;
  say: (text: string) => void;
  focusRow: (id: string) => void;
  level: number;
}) {
  const root = useRef<HTMLDivElement>(null);
  const fromRef = useRef<HTMLInputElement>(null);
  const toRef = useRef<HTMLInputElement>(null);
  const editRef = useRef<HTMLButtonElement>(null);
  const retryRef = useRef<HTMLButtonElement>(null);
  const uid = useId();
  const leaf = node.children.length === 0;
  const word = unit === "slide" ? "slide" : "trang";
  const [from, setFrom] = useState(state.from ?? String(node.from));
  const [to, setTo] = useState(state.to ?? String(node.to));
  const [error, setError] = useState<{ field: "from" | "to"; text: string } | null>(() => {
    if (!state.error) return null;
    const text = validateRange(Number(state.from), Number(state.to), rangeContext(nodes, node.id, total), unit);
    return text ? { field: "from", text } : null;
  });
  const [saveError, setSaveError] = useState(state.saveError ?? false);

  // Focus goes in only when the learner opened the panel; a lost focus (a button that vanished
  // after its own action) goes to the first button.
  useEffect(() => {
    if (state.focus) (state.mode === "edit" ? fromRef : editRef).current?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (state.mode === "actions" && document.activeElement === document.body) {
      root.current?.querySelector<HTMLButtonElement>("button")?.focus();
    }
  });

  const name = <span className="sr-only"> {node.title}</span>;
  const counts = markCounts(node);
  const markedDone = leaf ? node.done : false;

  function close(next: "row" | "edit-button") {
    setState(null);
    if (next === "row") focusRow(node.id);
  }

  function edit() {
    setState({ ...state, mode: "edit", focus: true });
  }

  function cancel() {
    setState({ id: node.id, mode: "actions", focus: false });
    queueMicrotask(() => editRef.current?.focus());
  }

  function save() {
    const f = Number(from);
    const t = Number(to);
    const text = validateRange(f, t, rangeContext(nodes, node.id, total), unit);
    if (text) {
      const field = !Number.isInteger(f) || f < 1 || f > t ? "from" : "to";
      setError({ field, text });
      queueMicrotask(() => (field === "from" ? fromRef : toRef).current?.focus());
      return;
    }
    onNodes(applyRange(nodes, node.id, f, t));
    setState(null);
    focusRow(node.id);
    say(`Đã lưu: mục ${node.title.split(" ")[0]} ${rangeText(f, t, unit)}.`);
  }

  function act(next: SyllabusNode[], text: string) {
    onNodes(next);
    say(text);
  }

  const onKey = (e: KeyboardEvent) => {
    if (e.key !== "Escape") return;
    e.stopPropagation();
    if (state.mode === "edit") cancel();
    else close("row");
  };

  return (
    <div
      ref={root}
      onKeyDown={onKey}
      data-panel={node.id}
      style={{ ["--lvl" as string]: level - 1 }}
      className={`${INDENT} pb-3`}
    >
      <div className="ml-[calc(28px+8px+20px+8px)] flex flex-col gap-1 max-sm:ml-7">
        {state.mode === "actions" ? (
          <div className="flex flex-wrap items-center gap-x-1">
            <Button ref={editRef} variant="quiet" onClick={edit}>
              Sửa khoảng {word}
              {name}
            </Button>
            {leaf ? (
              <Button
                variant="quiet"
                onClick={() =>
                  act(applyMark(nodes, node.id, !markedDone), markedDone ? "Đã đánh dấu chưa học." : "Đã đánh dấu đã học.")
                }
              >
                {markedDone ? "Đánh dấu chưa học" : "Đánh dấu đã học"}
                {name}
              </Button>
            ) : (
              <>
                {counts.toStudied > 0 && (
                  <Button
                    variant="quiet"
                    onClick={() => act(applyMark(nodes, node.id, true), `Đã đánh dấu ${counts.toStudied} mục đã học.`)}
                  >
                    Đánh dấu {counts.toStudied} mục chưa học là đã học
                    {name}
                  </Button>
                )}
                {counts.toUnstudied > 0 && (
                  <Button
                    variant="quiet"
                    onClick={() => act(applyMark(nodes, node.id, false), `Đã đánh dấu ${counts.toUnstudied} mục là chưa học.`)}
                  >
                    Đánh dấu {counts.toUnstudied} mục là chưa học
                    {name}
                  </Button>
                )}
              </>
            )}
            <Button
              variant="quiet"
              onClick={() => {
                const next = excludeToggle(nodes, node.id);
                const now = findNode(next, node.id)!;
                const count = countCountable({ ...now, excluded: false });
                act(
                  next,
                  now.excluded
                    ? leaf
                      ? "Mục này không thi."
                      : `Mục ${node.title.split(" ")[0]} không thi; ${count} mục con không tính.`
                    : "Đã đưa lại vào đề cương thi.",
                );
              }}
            >
              {node.excluded ? "Đưa lại" : "Bỏ khỏi đề cương thi"}
              {name}
            </Button>
          </div>
        ) : (
          <form
            method="post"
            onSubmit={(e) => {
              e.preventDefault();
              save();
            }}
            className="flex flex-col gap-3"
          >
            <div className="flex flex-wrap items-end gap-3">
              {(
                [
                  ["from", from, setFrom, fromRef, `Từ ${word}`],
                  ["to", to, setTo, toRef, `Đến ${word}`],
                ] as const
              ).map(([field, value, set, ref, text]) => (
                <label key={field} className="flex flex-col gap-1 text-meta text-ink-soft">
                  {text}
                  <Input
                    ref={ref}
                    inputMode="numeric"
                    value={value}
                    onChange={(e) => set(e.target.value)}
                    aria-invalid={error?.field === field || undefined}
                    aria-describedby={error?.field === field ? `${uid}-err` : undefined}
                    className="w-28"
                  />
                </label>
              ))}
            </div>
            {error && <FieldError id={`${uid}-err`}>{error.text}</FieldError>}
            {saveError && (
              <p role="alert" className="m-0 flex flex-wrap items-center gap-2 text-small">
                Chưa lưu được. Thử lại.
                <Button
                  ref={retryRef}
                  type="button"
                  variant="quiet"
                  onClick={() => {
                    setSaveError(false);
                    save();
                  }}
                >
                  Thử lại
                </Button>
              </p>
            )}
            <div className="flex items-center gap-2">
              <Button type="submit">Lưu</Button>
              <Button type="button" variant="quiet" onClick={cancel}>
                Hủy
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

export function SyllabusTree({ label, nodes, unit, total, onNodes, say, onEditing, initialPanel = null }: Props) {
  const [open, setOpen] = useState<Set<string>>(() => {
    const set = defaultOpen(nodes);
    // The panel of a static state must be visible, so the way down to it is open.
    if (initialPanel) {
      const rows = visibleRows(nodes, new Set(nodes.flatMap(function all(n): string[] { return [n.id, ...n.children.flatMap(all)]; })));
      for (let row = rows.find((r) => r.node.id === initialPanel.id); row?.parentId; ) {
        set.add(row.parentId);
        row = rows.find((r) => r.node.id === row!.parentId);
      }
    }
    return set;
  });
  const rows = visibleRows(nodes, open);
  const [active, setActive] = useState(initialPanel?.id ?? rows[0]?.node.id ?? "");
  const [panel, setPanelState] = useState<PanelState | null>(initialPanel);
  const items = useRef(new Map<string, HTMLLIElement>());
  const hintId = useId();
  const leafHintId = useId();

  const setPanel = (next: PanelState | null) => {
    setPanelState(next);
    onEditing(next?.mode === "edit");
  };
  useEffect(() => onEditing(initialPanel?.mode === "edit"), [initialPanel, onEditing]);

  const focusRow = (id: string) => {
    setActive(id);
    items.current.get(id)?.focus();
  };

  function fold(id: string, to: boolean) {
    const next = new Set(open);
    if (to) next.add(id);
    else {
      next.delete(id);
      // A fold that hides the focused row moves focus up to the branch.
      const node = findNode(nodes, id);
      const hidden = node ? visibleRows(node.children, open) : [];
      if (hidden.some((r) => r.node.id === active)) focusRow(id);
      if (panel && hidden.some((r) => r.node.id === panel.id)) setPanel(null);
    }
    setOpen(next);
  }

  function openPanel(id: string) {
    if (panel?.id === id) {
      setPanel(null);
      focusRow(id);
      return;
    }
    setActive(id);
    setPanel({ id, mode: "actions", focus: true });
  }

  function onKeyDown(e: KeyboardEvent<HTMLLIElement>, row: Row) {
    if (e.target !== e.currentTarget) return;
    const index = rows.findIndex((r) => r.node.id === row.node.id);
    const branch = row.node.children.length > 0;
    const go = (to: Row | undefined) => {
      if (to) focusRow(to.node.id);
    };
    switch (e.key) {
      case "ArrowDown":
        go(rows[index + 1]);
        break;
      case "ArrowUp":
        go(rows[index - 1]);
        break;
      case "Home":
        go(rows[0]);
        break;
      case "End":
        go(rows[rows.length - 1]);
        break;
      case "ArrowRight":
        if (branch && !open.has(row.node.id)) fold(row.node.id, true);
        else if (branch) go(rows[index + 1]);
        break;
      case "ArrowLeft":
        if (branch && open.has(row.node.id)) fold(row.node.id, false);
        else go(rows.find((r) => r.node.id === row.parentId));
        break;
      case "Enter":
      case " ":
        if (branch) fold(row.node.id, !open.has(row.node.id));
        else openPanel(row.node.id);
        break;
      case "ContextMenu":
        openPanel(row.node.id);
        break;
      case "F10":
        if (!e.shiftKey) return;
        openPanel(row.node.id);
        break;
      case "Escape":
        if (panel?.id !== row.node.id) return;
        setPanel(null);
        break;
      default:
        return;
    }
    e.preventDefault();
  }

  function renderList(list: SyllabusNode[], level: number, parentId: string | null): ReactNode {
    return list.map((node, i) => {
      const row: Row = { node, level, setSize: list.length, posInSet: i + 1, parentId };
      const branch = node.children.length > 0;
      const isOpen = open.has(node.id);
      const status = nodeStatus(node);
      const leaf = !branch;
      const range = rangeText(node.from, node.to, unit);
      const note = describeNode(node, unit);
      const visible = node.excluded
        ? "không thi"
        : status === "done" && leaf
          ? "đã học"
          : status === "partial" && leaf
            ? `đã học ${rangeText(node.part![0], node.part![1], unit)}`
            : branch
              ? note
              : null;
      const panelHere = panel?.id === node.id;
      return (
        <li
          key={node.id}
          ref={(el) => {
            if (el) items.current.set(node.id, el);
            else items.current.delete(node.id);
          }}
          // aria-selected is optional for a treeitem (APG); a tree of studied/unstudied has no selection.
          // eslint-disable-next-line jsx-a11y/role-has-required-aria-props
          role="treeitem"
          id={`ti-${node.id}`}
          aria-level={level}
          aria-setsize={list.length}
          aria-posinset={i + 1}
          aria-expanded={branch ? isOpen : undefined}
          aria-labelledby={`ti-${node.id}-t ti-${node.id}-m`}
          aria-describedby={`ti-${node.id}-d ${branch ? hintId : leafHintId}`}
          tabIndex={active === node.id ? 0 : -1}
          onFocus={(e) => {
            if (e.target === e.currentTarget) setActive(node.id);
          }}
          onKeyDown={(e) => onKeyDown(e, row)}
          data-node={node.id}
          data-status={status}
          className="list-none outline-none"
        >
          <div
            data-row
            style={{ ["--lvl" as string]: level - 1 }}
            onClick={() => (branch ? fold(node.id, !isOpen) : openPanel(node.id))}
            className={`${INDENT} flex min-h-11 cursor-pointer items-start gap-2 rounded-control py-2 [li:focus-visible>&]:outline-2 [li:focus-visible>&]:outline-offset-2 [li:focus-visible>&]:outline-focus`}
          >
            <span className="flex h-7 w-7 shrink-0 items-center justify-center">
              {branch && (
                <button
                  type="button"
                  tabIndex={-1}
                  aria-hidden="true"
                  data-chevron
                  className={`${HIT} flex h-7 w-7 items-center justify-center rounded-control text-ink-soft`}
                  onClick={(e) => {
                    e.stopPropagation();
                    fold(node.id, !isOpen);
                  }}
                >
                  <Chevron open={isOpen} />
                </button>
              )}
            </span>
            <span className="flex h-7 w-5 shrink-0 items-center justify-center" aria-hidden="true">
              {status === "done" && !node.excluded ? <Tick /> : status === "partial" && leaf && !node.excluded ? <Half /> : null}
            </span>
            <span className="flex min-w-0 flex-1 flex-col sm:flex-row sm:items-baseline sm:justify-between sm:gap-3">
              <span className="flex min-w-0 flex-col">
                <span id={`ti-${node.id}-t`} data-user className={`wrap-anywhere text-body ${node.excluded ? "text-ink-soft" : ""} ${branch ? "font-semibold" : ""}`}>
                  {node.title}
                </span>
                {visible && (
                  <span className="text-small text-ink-soft">
                    {visible}
                  </span>
                )}
              </span>
              <span id={`ti-${node.id}-m`} className="shrink-0 text-small text-ink-soft">
                {range}
              </span>
            </span>
            <button
              type="button"
              tabIndex={active === node.id ? 0 : -1}
              aria-label={`Hành động cho ${node.title}`}
              aria-expanded={panelHere}
              data-more
              className={`${HIT} flex h-7 w-7 shrink-0 items-center justify-center rounded-control text-ink-soft focus-visible:outline-2 focus-visible:outline-focus`}
              onClick={(e) => {
                e.stopPropagation();
                openPanel(node.id);
              }}
            >
              <Dots />
            </button>
          </div>
          <span id={`ti-${node.id}-d`} className="sr-only">
            {note}
          </span>
          {panelHere && panel && (
            <Panel
              key={`${panel.id}-${panel.mode}`}
              node={node}
              unit={unit}
              nodes={nodes}
              total={total}
              state={panel}
              setState={setPanel}
              onNodes={onNodes}
              say={say}
              focusRow={focusRow}
              level={level}
            />
          )}
          {branch && isOpen && (
            <ul role="group" className="m-0 list-none p-0">
              {renderList(node.children, level + 1, node.id)}
            </ul>
          )}
        </li>
      );
    });
  }

  return (
    <>
      <span id={hintId} className="sr-only">
        Nhấn Enter để mở hoặc đóng nhánh
      </span>
      <span id={leafHintId} className="sr-only">
        Nhấn Enter để sửa
      </span>
      <ul role="tree" aria-label={label} className="m-0 list-none p-0">
        {renderList(nodes, 1, null)}
      </ul>
    </>
  );
}
