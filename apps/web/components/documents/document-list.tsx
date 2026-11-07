import { ArrowRight, TriangleAlert } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { BackLink, Block } from "@/components/screen-kit";
import { PageColumn } from "@/components/shells";
import { Button } from "@/components/ui/button";

// C4 (v4): one white sheet of rows, a plum field only when something needs the reader. T4.9 (US-01): a subject's documents with their processing state (screens-html/screens/subject.html,
// ".docs"). Sentences from the mockup are final; the failure ones are placeholders (risk register R09).
export type ListedDocument = {
  id: string;
  short_name: string;
  status: string;
  page_count: number | null;
  unreadable_pages: number[];
  failure_reason: string | null;
  role?: string;
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

/** A doc's state as one word for the structure: reading, ready, partly unreadable, or failed. */
export type DocState = "reading" | "ready" | "partial" | "failed";
export const docState = (doc: ListedDocument): DocState =>
  doc.status === "pending" ? "reading" : doc.status !== "indexed" ? "failed" : doc.unreadable_pages.length === 0 ? "ready" : "partial";

// "Đang đọc" has a sign of motion (a ring that turns, still under reduced motion); a failure is a
// chip in --partial with a mark, so neither reads as plain grey text.
function Status({ doc }: { doc: ListedDocument }) {
  const state = docState(doc);
  if (state === "reading") {
    return (
      <span data-doc-state="reading" className="inline-flex items-center gap-2">
        <span aria-hidden="true" className="size-3.5 shrink-0 rounded-full border-2 border-line-strong border-t-hong motion-safe:animate-spin" />
        Đang đọc tài liệu…
      </span>
    );
  }
  if (state === "ready") return <span data-doc-state="ready">Sẵn sàng</span>;
  const text = state === "partial" ? unreadableText(doc.unreadable_pages) : failureText(doc.failure_reason);
  return (
    <span
      data-doc-state={state}
      className="inline-flex items-start gap-1.5 font-medium text-partial"
    >
      <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      {state === "failed" ? <span data-copy="tam">{failureText(doc.failure_reason)}</span> : text}
    </span>
  );
}

const ROW = "flex items-center gap-4 rounded-row p-3 min-[641px]:px-5 min-[641px]:py-4";

function Cells({ doc, linked }: { doc: ListedDocument; linked: boolean }) {
  return (
    <>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="font-display text-lead wrap-anywhere">{doc.short_name}</span>
        <span className="text-meta text-ink-soft">
          <Status doc={doc} />
          {doc.page_count !== null ? ` · ${doc.page_count} trang` : ""}
        </span>
      </span>
      {linked ? <ArrowRight aria-hidden="true" className="size-5 shrink-0 text-ink-soft" /> : null}
    </>
  );
}

export function DocumentList({ subjectId, docs }: { subjectId: string; docs: ListedDocument[] }) {
  const upload = (
    <Button render={<a href={`/subjects/${subjectId}/upload`} />} nativeButton={false}>
      Tải tài liệu lên
    </Button>
  );
  if (docs.length === 0) {
    return (
      <Block as="section" tier="sheet" aria-label="Chưa có tài liệu">
        <EmptyState
          mascot="cho"
          title="Chưa có tài liệu."
          hint="Tải giáo trình, slide hoặc ảnh vở để app biết bạn học từ đâu."
          action={upload}
        />
      </Block>
    );
  }
  return (
    <div className="flex flex-col items-start gap-5">
      <Block as="section" tier="sheet" aria-label="Tài liệu" className="w-full p-2 min-[901px]:p-2">
        <ul className="m-0 flex list-none flex-col p-0">
          {docs.map((doc) => {
            const href =
              doc.status !== "indexed"
                ? null
                : doc.role === "textbook"
                  ? `/subjects/${subjectId}/syllabus`
                  : `/subjects/${subjectId}/documents/${doc.id}`;
            return (
              <li key={doc.id} className="border-t border-line first:border-t-0">
                {href ? (
                  <a href={href} className={`${ROW} text-ink no-underline hover:bg-sunken`}>
                    <Cells doc={doc} linked />
                  </a>
                ) : (
                  <div className={ROW}>
                    <Cells doc={doc} linked={false} />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </Block>
      {upload}
    </div>
  );
}

export function DocumentsFrame({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <PageColumn width="full" className="flex flex-col gap-5">
      <header className="flex flex-col gap-2">
        <BackLink href="/subjects">Môn học</BackLink>
        <h1 className="m-0 text-title wrap-anywhere">{name}</h1>
      </header>
      {children}
    </PageColumn>
  );
}
