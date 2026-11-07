import { Block } from "@/components/screen-kit";
import { unreadableText } from "@/components/documents/document-list";
import type { TocNode } from "@/lib/toc";

// T4.9 (US-02 AC2): the table of contents as a tree (screens-html/screens/toc.html, ".toc": 28 px
// of indent per level). The page range is soft text, as the mockup has it.
function range(node: TocNode): string | null {
  if (node.from === null || node.to === null) return null;
  return node.to > node.from ? `tr. ${node.from}–${node.to}` : `tr. ${node.from}`;
}

function Branch({ nodes, depth }: { nodes: TocNode[]; depth: number }) {
  return (
    <ul className="m-0 list-none p-0" style={depth > 0 ? { paddingLeft: 28 } : undefined}>
      {nodes.map((node, i) => (
        <li key={`${i}-${node.title}`}>
          <div className="flex items-baseline justify-between gap-3 py-2">
            <span className={`min-w-0 wrap-anywhere ${depth === 0 ? "font-display text-lead" : "text-body"}`}>{node.title}</span>
            {range(node) && <span className="shrink-0 text-meta text-ink-soft">{range(node)}</span>}
          </div>
          {node.children.length > 0 && <Branch nodes={node.children} depth={depth + 1} />}
        </li>
      ))}
    </ul>
  );
}

export function TocTree({ nodes }: { nodes: TocNode[] }) {
  if (nodes.length === 0) {
    return (
      <Block as="section" tier="sheet">
        <p className="m-0 text-body text-ink-soft" data-copy="tam">
          Tài liệu này không có mục lục.
        </p>
      </Block>
    );
  }
  return (
    <Block as="section" tier="sheet" aria-label="Mục lục" className="p-4 min-[901px]:px-8 min-[901px]:py-6">
      <Branch nodes={nodes} depth={0} />
    </Block>
  );
}

/** Pages the reader could not get text from: shown above the tree, with words and a shape. */
export function UnreadableNotice({ pages }: { pages: number[] }) {
  if (pages.length === 0) return null;
  return (
    <p role="status" className="m-0 flex items-center gap-2 rounded-control bg-hong-tint px-4 py-3 text-meta font-semibold">
      <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
        <path d="M8 1.75 14.5 13.5h-13z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
        <path d="M8 6.5v3.25" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="8" cy="11.6" r=".9" fill="currentColor" />
      </svg>
      {unreadableText(pages)}
    </p>
  );
}

const BOX = "m-0 rounded-tile border border-line bg-sheet p-6 text-body";

export function TocUnreadable() {
  return (
    <p role="alert" className={BOX} data-copy="tam">
      Chưa đọc được mục lục của tài liệu này.
    </p>
  );
}

export function TocNotReady() {
  return (
    <p role="status" className={BOX} data-copy="tam">
      Tài liệu này chưa đọc xong. Mục lục sẽ hiện khi đọc xong.
    </p>
  );
}
