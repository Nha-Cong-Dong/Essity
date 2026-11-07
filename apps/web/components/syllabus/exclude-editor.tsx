"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { SyllabusNode } from "@/lib/syllabus/tree";

// Hackathon E4: "Chỉnh sửa" shows a checkbox per section; ticked rows turn red; "Bỏ khỏi đề cương"
// removes them (the existing exclude PATCH, sent by the parent's `onExclude`).

function Rows({
  nodes,
  depth,
  picked,
  toggle,
}: {
  nodes: SyllabusNode[];
  depth: number;
  picked: ReadonlySet<string>;
  toggle: (id: string) => void;
}) {
  return (
    <ul className="m-0 list-none p-0">
      {nodes.map((n) => {
        const on = picked.has(n.id);
        return (
          <li key={n.id}>
            <label
              data-picked={on ? "true" : "false"}
              className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-control px-2 text-body wrap-anywhere ${on ? "bg-hong-tint text-hong-text" : n.excluded ? "text-ink-soft line-through" : ""}`}
              style={{ marginLeft: `${depth * 20}px` }}
            >
              <input type="checkbox" checked={on} disabled={n.excluded} onChange={() => toggle(n.id)} className="size-5 shrink-0" />
              <span className={n.children.length > 0 ? "font-semibold" : ""}>{n.title}</span>
            </label>
            {n.children.length > 0 && <Rows nodes={n.children} depth={depth + 1} picked={picked} toggle={toggle} />}
          </li>
        );
      })}
    </ul>
  );
}

export function ExcludeEditor({ nodes, onExclude, onCancel }: { nodes: SyllabusNode[]; onExclude: (ids: string[]) => void; onCancel: () => void }) {
  const [picked, setPicked] = useState<ReadonlySet<string>>(new Set());
  const toggle = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  return (
    <div className="flex flex-col gap-4" data-exclude-editor>
      <Rows nodes={nodes} depth={0} picked={picked} toggle={toggle} />
      <div className="flex flex-wrap items-center gap-3">
        <Button disabled={picked.size === 0} onClick={() => onExclude([...picked])}>
          Bỏ khỏi đề cương
        </Button>
        <Button variant="quiet" onClick={onCancel}>
          Xong
        </Button>
      </div>
    </div>
  );
}
