import { type CardSource, sourceLabel, splitMarked } from "@/lib/card-source";

// G4: the page a card came from, with the cited passage in <mark>. Page text is the extracted text
// of the page; the original file is not opened here (no read link for raw files yet).
export function SourceView({ source }: { source: CardSource }) {
  const parts = source.page_text === null ? null : splitMarked(source.page_text, source.mark_start, source.mark_end);
  const quote = (
    <blockquote className="m-0 mt-2 border-l-4 border-line pl-3 whitespace-pre-wrap">
      <mark>{source.quote}</mark>
    </blockquote>
  );
  return (
    <section className="rounded-sheet bg-sheet p-6 shadow-sheet" data-source>
      <h2 className="m-0 text-lg font-semibold">{sourceLabel(source)}</h2>
      {parts === null ? (
        <>
          <p className="mt-3 mb-0 text-ink-soft">Không đọc được nội dung trang này. Đoạn đã trích:</p>
          {quote}
        </>
      ) : (
        <>
          <p className="mt-3 mb-0 whitespace-pre-wrap text-read leading-relaxed">
            {parts.map((p, i) => (p.marked ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>))}
          </p>
          {source.mark_start === null && (
            <>
              <p className="mt-3 mb-0 text-ink-soft">Không tìm thấy đúng đoạn trong trang. Đoạn đã trích:</p>
              {quote}
            </>
          )}
        </>
      )}
    </section>
  );
}
