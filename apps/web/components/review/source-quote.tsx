import type { Result } from "@/lib/review-client";

// T2.16 (DESIGN.md §6.5, US-05 AC2): a line the grade used, quoted under a 1px rule in ink with
// the thin pink band of the highlighter, then where it comes from. The source panel (§6.6) that
// opens from the citation comes later; until then the citation is plain text.

type Source = Result["sources"][number];

function SourceCite({ source }: { source: Source }) {
  if (source.kind === "notes") return <span data-copy="tam">Vở ghi</span>;
  if (source.page_no === null) return <span data-copy="tam">Giáo trình</span>;
  return <span data-copy="tam">Giáo trình · tr. {source.page_no}</span>;
}

export function SourceQuote({ source }: { source: Source }) {
  return (
    <figure className="m-0">
      <blockquote className="m-0 border-l border-line-strong pl-3.5 text-body leading-[1.75] wrap-anywhere">
        <mark className="animate-hl-sweep [background:linear-gradient(var(--hl-band),var(--hl-band))_0_100%/100%_38%_no-repeat] px-px text-ink [box-decoration-break:clone]">
          {source.quote_text}
        </mark>
      </blockquote>
      <figcaption className="mt-1 pl-3.75 text-meta text-ink-soft">
        <SourceCite source={source} />
      </figcaption>
    </figure>
  );
}
