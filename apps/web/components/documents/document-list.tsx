import { Marker } from "@/components/notebook";

// T4.9 (US-01): a subject's documents with their processing state (screens-html/screens/subject.html,
// ".docs"). Sentences from the mockup are final; the failure ones are placeholders (risk register R09).
export type ListedDocument = {
  id: string;
  short_name: string;
  status: string;
  page_count: number | null;
  unreadable_pages: number[];
  failure_reason: string | null;
};

const SHOWN_PAGES = 8;

const FAILURES: Record<string, string> = {
  encrypted: "File có mật khẩu nên chưa đọc được.",
  corrupt: "File bị lỗi nên chưa đọc được.",
  too_many_pages: "File quá nhiều trang nên chưa đọc được.",
  content_mismatch: "File này không phải PDF hợp lệ.",
};
const FAILURE_FALLBACK = "Chưa đọc được tài liệu này.";

export const failureText = (reason: string | null): string => (reason && FAILURES[reason]) || FAILURE_FALLBACK;

/** "Không đọc được 3 trang (tr. 12, 13, 40)", cut after a few pages so a long list stays one line. */
export function unreadableText(pages: number[]): string {
  const shown = pages.slice(0, SHOWN_PAGES).join(", ");
  const more = pages.length > SHOWN_PAGES ? ", …" : "";
  return `Không đọc được ${pages.length} trang (tr. ${shown}${more})`;
}

function Status({ doc }: { doc: ListedDocument }) {
  if (doc.status === "pending") return <span className="text-ink-soft">Đang đọc tài liệu…</span>;
  if (doc.status === "indexed" && doc.unreadable_pages.length === 0) return <span>Sẵn sàng</span>;
  if (doc.status === "indexed") return <span>{unreadableText(doc.unreadable_pages)}</span>;
  return <span data-copy="tam">{failureText(doc.failure_reason)}</span>;
}

export function DocumentList({ subjectId, docs }: { subjectId: string; docs: ListedDocument[] }) {
  if (docs.length === 0) {
    return (
      <div className="flex flex-col items-start gap-2 rounded-sheet bg-sunken p-6">
        <p className="m-0 text-section font-semibold">Chưa có tài liệu.</p>
        <p className="m-0 text-body text-ink-soft">
          Tải giáo trình, slide hoặc ảnh vở để app biết bạn học từ đâu.
        </p>
        <a href={`/subjects/${subjectId}/upload`} className="mt-3 font-semibold underline">
          Tải tài liệu lên
        </a>
      </div>
    );
  }
  return (
    <>
      <ul className="m-0 flex list-none flex-col gap-3 p-0" aria-label="Tài liệu">
        {docs.map((doc) => (
          <li key={doc.id} className="flex flex-col gap-1 rounded-sheet bg-sunken p-4">
            <span className="min-w-0 text-section font-semibold wrap-anywhere">
              {doc.status === "indexed" ? (
                <a href={`/subjects/${subjectId}/documents/${doc.id}`} className="underline">
                  {doc.short_name}
                </a>
              ) : (
                doc.short_name
              )}
            </span>
            <span className="text-small">
              <Status doc={doc} />
            </span>
            {doc.page_count !== null && <span className="text-small text-ink-soft">{doc.page_count} trang</span>}
          </li>
        ))}
      </ul>
      <p className="mt-4 mb-0">
        <a href={`/subjects/${subjectId}/upload`} className="font-semibold underline">
          Tải tài liệu lên
        </a>
      </p>
    </>
  );
}

export function DocumentsFrame({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-220 flex-col">
      <a href="/subjects" className="mb-4 self-start text-small underline">
        Môn học
      </a>
      <h1 className="m-0 mb-8 font-display text-title wrap-anywhere">
        <Marker>{name}</Marker>
      </h1>
      {children}
    </div>
  );
}
