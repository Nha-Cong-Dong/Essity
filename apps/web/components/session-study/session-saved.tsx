"use client";

import Link from "next/link";

import { Button, buttonVariants } from "@/components/ui/button";

// T7.12a (DESIGN.md §6.7 vùng 5; design decision C13): after Lưu. The saved cards fold into three
// lines (the wording follows what was covered), then "Học tiếp hay dừng?" with two secondary
// buttons of the same size and no primary: nothing pushes the learner either way.

export type SavedKind = "section" | "partial" | "free";

export function SavedArea({
  kind,
  count,
  stopHref,
  onContinue,
}: {
  kind: SavedKind;
  count: number;
  stopHref: string;
  onContinue: () => void;
}) {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1 text-body">
        <p className="m-0">{kind === "free" ? `Đã lưu ${count} thẻ.` : `Đã lưu ${count} thẻ cho mục 3.2.`}</p>
        {kind === "section" && <p className="m-0">Mục 3.2 đã học.</p>}
        {kind === "partial" && <p className="m-0">Đã học tr. 52-55 của mục 3.2.</p>}
        <p className="m-0 text-ink-soft">Thẻ mới vào ôn từ ngày học kế tiếp.</p>
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
