import { Sheet } from "@/components/ui/sheet";

// V21: the last numbered card of adding a subject: what happens once the textbook is in.
const STEPS = [
  { text: "Đọc mục lục giáo trình", tag: "tự động" },
  { text: "Dựng đề cương theo chương", tag: "tự động" },
  { text: "Bạn xem lại và tùy chỉnh", tag: "bạn làm" },
] as const;

export function OutlineCard({ className }: { className?: string }) {
  return (
    <Sheet variant="tile" tone="rose" className={className} aria-labelledby="docs-outline">
      <h2 id="docs-outline" className="m-0 font-display text-lead">
        3. Đề cương sẽ ra sao?
      </h2>
      <ul className="m-0 mt-4 flex list-none flex-col gap-3 p-0">
        {STEPS.map((step) => (
          <li key={step.text} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-read">
            <span>{step.text}</span>
            <span className="rounded-slip bg-sheet px-2 py-0.5 text-meta font-semibold text-ink-soft">{step.tag}</span>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}
