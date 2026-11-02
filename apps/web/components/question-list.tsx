import { Badge } from "@/components/ui/badge";
import type { QuestionListOut, QuestionRow } from "@/lib/question-list-types";

// T8.2 (US-14 AC3-AC6; DESIGN §6.12): the bank's questions, by type, each with its one status
// line. Rows have no actions yet (T8.7 adds "Làm câu này" and the rest). Rows are readable at 320
// px: one column, long text wraps. The wording of the status line comes from the backend.

const OTHER_TYPE = "Chưa có dạng";

function Row({ q, subjectId }: { q: QuestionRow; subjectId: string }) {
  return (
    <li data-question={q.id} className="flex flex-col gap-2 border-t border-line py-4 first:border-t-0">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Badge variant="level">{q.origin === "bank" ? "Câu gốc" : "Câu sinh thêm"}</Badge>
        {q.status === "ready" && <span className="text-meta">{q.line}</span>}
        {q.status === "waiting" && (
          <a href={`/subjects/${subjectId}/syllabus`} className="text-meta underline">
            {q.line}
          </a>
        )}
        {q.status === "unlinked" && <span className="text-meta text-ink-soft">Chưa gắn mục</span>}
        {q.number !== null && <span className="text-meta text-ink-soft">Câu {q.number}</span>}
      </div>
      <p data-user className="m-0 line-clamp-3 wrap-anywhere">
        {q.prompt}
      </p>
      {q.answer_source === "ai" && <span className="font-hand text-body text-pencil">đáp án do AI soạn</span>}
    </li>
  );
}

function groupByType(rows: QuestionRow[]): [string, QuestionRow[]][] {
  const groups = new Map<string, QuestionRow[]>();
  for (const row of rows) groups.set(row.type_name, [...(groups.get(row.type_name) ?? []), row]);
  return [...groups].sort(([a], [b]) => (a === "" ? 1 : b === "" ? -1 : 0));
}

export function QuestionList({ subjectId, list }: { subjectId: string; list: QuestionListOut }) {
  if (list.total === 0) {
    return (
      <p className="m-0 text-ink-soft" data-empty>
        Chưa có bộ câu hỏi. Tải một bộ câu hỏi ở mục Tài liệu để bắt đầu.
      </p>
    );
  }
  const unlinked = list.questions.filter((q) => q.status === "unlinked");
  const linked = list.questions.filter((q) => q.status !== "unlinked");
  return (
    <div className="flex flex-col gap-6">
      <p className="m-0" data-summary>
        {list.total} câu · {list.ready} sẵn sàng
      </p>
      {groupByType(linked).map(([type, rows]) => (
        <section key={type || "none"} aria-label={type || OTHER_TYPE}>
          <h2 className="m-0 text-body font-semibold">
            {type || OTHER_TYPE} <span className="font-normal text-ink-soft">({rows.length})</span>
          </h2>
          <ul className="m-0 mt-2 flex list-none flex-col p-0">
            {rows.map((q) => (
              <Row key={q.id} q={q} subjectId={subjectId} />
            ))}
          </ul>
        </section>
      ))}
      {unlinked.length > 0 && (
        <section aria-label="Chưa gắn mục">
          <h2 className="m-0 text-body font-semibold">
            Chưa gắn mục <span className="font-normal text-ink-soft">({unlinked.length})</span>
          </h2>
          <p className="m-0 mt-1 text-ink-soft">Chưa gắn mục. Sửa bằng thanh lệnh.</p>
          <ul className="m-0 mt-2 flex list-none flex-col p-0">
            {unlinked.map((q) => (
              <Row key={q.id} q={q} subjectId={subjectId} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
