import { outlineView } from "@/lib/syllabus/api";
import type { OutlineOut } from "@/lib/syllabus/api";
import { progress } from "@/lib/syllabus/tree";

// T7.13b (DESIGN §6.5 item 4): the entry row of the subject screen. Each entry shows only when its
// target screen has something to show; a source that failed to load (null) drops its entry and
// never breaks the row. Stats has no per-subject count in the API, so its entry has no number.

export type SubjectEntry = { key: "syllabus" | "practice" | "stats" | "graph"; label: string; href: string; note: string | null };

export type EntrySources = {
  outline: OutlineOut | null;
  /** Ready and total of the bank questions (QuestionListOut), null when unread. */
  questions: { ready: number; total: number } | null;
  /** Cards in the graph, null when unread. */
  graphCards: number | null;
};

export function entryRow(subjectId: string, src: EntrySources): SubjectEntry[] {
  const base = `/subjects/${subjectId}`;
  const entries: SubjectEntry[] = [];
  const view = src.outline === null ? null : outlineView(src.outline);
  if (view?.kind === "ready") {
    const p = progress(view.nodes);
    entries.push({ key: "syllabus", label: "Đề cương", href: `${base}/syllabus`, note: `đã học ${p.done}/${p.total} mục` });
  }
  if (src.questions !== null && src.questions.total > 0) {
    entries.push({ key: "practice", label: "Luyện tập", href: `${base}/practice`, note: `${src.questions.ready} câu sẵn sàng` });
  }
  entries.push({ key: "stats", label: "Thống kê", href: `/stats?subject=${subjectId}`, note: null });
  // J1 (T9.10d): the tile is always there; an empty graph leads to "Ghi buổi học".
  entries.push({
    key: "graph",
    label: "Đồ thị tri thức",
    href: `${base}/graph`,
    note: src.graphCards !== null && src.graphCards > 0 ? `${src.graphCards} thẻ` : "chưa có thẻ",
  });
  return entries;
}
