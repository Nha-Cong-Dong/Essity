import type { ReactNode } from "react";

// T8.7a, T8.7: small pieces of the practice screens shared by the fixture screen and the live one.

export function Pen({ children }: { children: ReactNode }) {
  return <span className="font-hand text-body text-pencil">{children}</span>;
}

/** What a practice result adds to GradeResult (which already shows the rubric per idea). */
export function PracticeResultExtras({
  timing,
  differsFromCard,
  answerSource,
}: {
  /** Only when the grade says the time is usable (timing_ok). */
  timing?: { seconds: number; refMinutes: number };
  /** The API gives the card's id only: with no label and link the line says so plainly. */
  differsFromCard?: { label?: string; href?: string } | true;
  answerSource: "bank" | "ai";
}) {
  const minutes = timing ? Math.floor(timing.seconds / 60) : 0;
  const seconds = timing ? timing.seconds % 60 : 0;
  return (
    <div data-practice-extras className="mt-6.5 flex flex-col gap-3">
      {answerSource === "ai" && <Pen>đáp án do AI soạn</Pen>}
      {differsFromCard && (
        <p className="m-0 wrap-anywhere">
          {differsFromCard === true || !differsFromCard.label || !differsFromCard.href ? (
            "Đáp án này khác với một thẻ bạn đã học."
          ) : (
            <>
              Đáp án này khác với thẻ{" "}
              <a href={differsFromCard.href} className="underline">
                {differsFromCard.label}
              </a>
              .
            </>
          )}
        </p>
      )}
      {timing && (
        <p className="m-0 text-ink-soft">
          Bạn trả lời trong {minutes} phút{seconds ? ` ${seconds} giây` : ""}. Dạng này thường mất khoảng{" "}
          {timing.refMinutes} phút.
        </p>
      )}
    </div>
  );
}
