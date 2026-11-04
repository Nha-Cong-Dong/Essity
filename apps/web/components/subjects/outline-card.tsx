// V22: what happens after the textbook is in, as three plain lines under the form (no card, no chips).
const STEPS = [
  "Essity đọc mục lục giáo trình (tự động).",
  "Essity dựng đề cương theo chương (tự động).",
  "Bạn xem lại và tùy chỉnh đề cương.",
] as const;

export function OutlineCard({ className }: { className?: string }) {
  return (
    <section aria-labelledby="docs-outline" className={className}>
      <h2 id="docs-outline" className="m-0 text-body font-semibold">
        Đề cương sẽ ra sao?
      </h2>
      <ol className="m-0 mt-2 flex list-none flex-col gap-1 p-0 text-body text-ink-soft">
        {STEPS.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
    </section>
  );
}
