"use client";

import Link from "next/link";

import { Mascot } from "@/components/mascot";
import { Button, buttonVariants } from "@/components/ui/button";
import type { SessionResult } from "@/lib/session-study/round";

// CARDS-V3 (was T7.12a vùng 5): after a finished read. The cards are already in the Kho (the
// learner edits or deletes them there), so there is nothing to approve: this says how many went in
// and under which session name, or, with none, says so and points to the outline. Then "Học tiếp
// hay dừng?" with two secondary buttons of the same size and no primary.

const link = "inline-flex min-h-11 items-center justify-center self-start rounded-full bg-sheet px-4 text-body font-medium text-ink no-underline inset-ring-1 inset-ring-line-strong hover:bg-sunken";

export function DoneArea({
  result,
  subjectId,
  sessionId,
  stopHref,
  onContinue,
}: {
  result: SessionResult;
  subjectId?: string;
  sessionId: string;
  stopHref: string;
  onContinue: () => void;
}) {
  const found = result.cards > 0;
  return (
    <div data-surface={found ? "rose" : undefined} className={`flex flex-col gap-6 rounded-tile p-6 min-[901px]:p-8 ${found ? "" : "bg-sunken"}`}>
      <div className="flex items-center gap-5">
        {found && <Mascot kind="sun" pose="chucmung" size="md" className="max-sm:size-24" />}
        <div className="flex flex-col gap-1 text-body">
          {found ? (
            <>
              <p className="m-0">Đã thêm {result.cards} thẻ vào Kho.</p>
              {result.title && <p className="m-0 text-ink-soft wrap-anywhere">Buổi học: {result.title}</p>}
              {subjectId && (
                <Link href={`/kho-kien-thuc?subject=${subjectId}&session=${sessionId}`} className={link}>
                  Xem trong Kho kiến thức
                </Link>
              )}
            </>
          ) : (
            <>
              <p className="m-0">Chưa tìm thấy nội dung để làm thẻ.</p>
              <p className="m-0 text-ink-soft">Thử chọn một mục từ đề cương rồi học lại.</p>
              {subjectId && (
                <Link href={`/subjects/${subjectId}/syllabus`} className={link}>
                  Chọn mục từ đề cương
                </Link>
              )}
            </>
          )}
        </div>
      </div>
      <div className="flex flex-col gap-3">
        <h3 className="m-0 font-display text-lead">Học tiếp hay dừng?</h3>
        <div className="flex flex-col gap-3 min-[481px]:flex-row">
          <Button type="button" variant="secondary" className="max-[480px]:w-full" onClick={onContinue}>
            Học tiếp
          </Button>
          <Link href={stopHref} className={buttonVariants({ variant: "secondary", className: "max-[480px]:w-full" })}>
            Dừng
          </Link>
        </div>
      </div>
    </div>
  );
}
