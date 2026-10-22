import type { ReactNode } from "react";

import { GridCorner, PageFold, Sticker } from "@/components/motifs";
import { NhanVo, NotebookCover } from "@/components/notebook";
import { AuthShell } from "@/components/shells";

/**
 * One account screen: the account frame, the notebook cover with the title, and the label holding
 * the form. Motifs (design system v3.1 §4.10): the grid in two opposite corners of the page, a
 * folded corner on the label and the pen sticker on the cover — three kinds, none behind text.
 */
export function AuthCard({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <AuthShell>
      <GridCorner corner="tl" />
      <GridCorner corner="br" />
      <div className="relative z-1 w-full max-w-[520px]">
        <Sticker icon="pen" className="-top-6 -right-3 min-[561px]:-right-6" />
        <NotebookCover title={title}>
          <NhanVo className="flex flex-col gap-5">
            <PageFold />
            {children}
          </NhanVo>
        </NotebookCover>
      </div>
    </AuthShell>
  );
}
