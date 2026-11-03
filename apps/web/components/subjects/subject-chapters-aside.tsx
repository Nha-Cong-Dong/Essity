import type { SyllabusNode } from "@/lib/syllabus/tree";

// Hackathon D3: read-only outline beside the subject page. A leaf is ticked by the system (it is
// studied), never by the learner. "Tùy chỉnh đề cương" leads to the customise screen.

function Row({ node, depth }: { node: SyllabusNode; depth: number }) {
  const leaf = node.children.length === 0;
  const ticked = leaf ? node.done : node.children.every((c) => c.excluded || isTicked(c));
  return (
    <li>
      <div
        className={`flex items-start gap-2 py-1 text-small wrap-anywhere ${node.excluded ? "text-ink-soft line-through" : ""} ${leaf ? "" : "font-semibold"}`}
        style={{ paddingLeft: `${depth * 12}px` }}
      >
        <span
          aria-hidden="true"
          data-ticked={ticked ? "true" : "false"}
          className={`mt-0.5 inline-flex size-4 shrink-0 items-center justify-center rounded-control border border-line text-meta leading-none ${ticked ? "bg-ink text-paper" : ""}`}
        >
          {ticked ? "✓" : ""}
        </span>
        <span>
          {node.title}
          <span className="sr-only">{ticked ? " (đã học)" : " (chưa học)"}</span>
        </span>
      </div>
      {!leaf && (
        <ul className="m-0 list-none p-0">
          {node.children.map((c) => (
            <Row key={c.id} node={c} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}

function isTicked(n: SyllabusNode): boolean {
  return n.children.length === 0 ? n.done : n.children.every((c) => c.excluded || isTicked(c));
}

export function SubjectOutlineAside({ nodes, subjectId }: { nodes: SyllabusNode[]; subjectId: string }) {
  return (
    <aside aria-label="Đề cương" className="flex min-w-0 flex-col gap-3 rounded-sheet bg-sunken p-4 lg:max-h-[80vh] lg:overflow-y-auto">
      <h2 className="m-0 font-display text-lead">Đề cương</h2>
      <ul className="m-0 flex list-none flex-col p-0">
        {nodes.map((n) => (
          <Row key={n.id} node={n} depth={0} />
        ))}
      </ul>
      <div className="flex justify-end">
        <a href={`/subjects/${subjectId}/syllabus`} className="inline-flex min-h-11 items-center text-small font-semibold underline">
          Tùy chỉnh đề cương
        </a>
      </div>
    </aside>
  );
}
