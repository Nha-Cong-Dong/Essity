import type { ReactNode } from "react";

import { NhanVo, NotebookCover } from "@/components/notebook";
import { AuthShell } from "@/components/shells";

/**
 * One account screen (DESIGN.md §6.1): the account frame, a straight 520px notebook cover with
 * the title, and the label holding the form.
 */
export function AuthCard({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <AuthShell>
      <div className="w-full max-w-[520px]">
        <NotebookCover title={title}>
          <NhanVo className="flex flex-col gap-5">{children}</NhanVo>
        </NotebookCover>
      </div>
    </AuthShell>
  );
}
