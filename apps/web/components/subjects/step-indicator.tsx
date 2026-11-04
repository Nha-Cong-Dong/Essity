// V12: where the learner is in adding a subject: 1 Tạo môn, 2 Tải tài liệu.
const STEPS = ["Tạo môn", "Tải tài liệu"] as const;

export function StepIndicator({ current }: { current: 1 | 2 }) {
  return (
    <ol aria-label="Các bước thêm môn" className="m-0 flex list-none items-center gap-2 p-0 text-small">
      {STEPS.map((label, index) => {
        const step = index + 1;
        const here = step === current;
        return (
          <li key={label} className="flex items-center gap-2" aria-current={here ? "step" : undefined}>
            {index > 0 ? <span aria-hidden="true" className="h-px w-8 bg-line-strong" /> : null}
            <span
              aria-hidden="true"
              className={`grid size-7 place-items-center rounded-full font-semibold ${here ? "bg-hong text-on-hong" : "bg-sunken text-ink-soft"}`}
            >
              {step}
            </span>
            <span className={here ? "font-semibold" : "text-ink-soft"}>{label}</span>
          </li>
        );
      })}
    </ol>
  );
}
