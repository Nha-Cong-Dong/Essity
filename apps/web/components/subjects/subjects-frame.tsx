import type { ReactNode } from "react";

import { Marker } from "@/components/notebook";

/**
 * The /subjects column and its title (DESIGN.md §6.8), drawn by each state of the page: loading,
 * failed, and SubjectList (listed or empty). The title shares a wrapping row with `action` ("Tạo
 * môn" beside a list): where they do not fit side by side (a narrow screen, enlarged text), the
 * button goes under the title, left (T2.3c, risk register R44, plan G15). The row keeps the
 * button's height, so the list moves only when the button wraps. The layout fixture
 * (/design-preview/subjects) renders SubjectList, so it measures this same frame.
 */
export function SubjectsFrame({ action, children }: { action?: ReactNode; children: ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-220 flex-col">
      <div className="mb-8 flex min-h-13 flex-wrap items-center justify-between gap-x-4 gap-y-4">
        <h1 className="m-0 font-display text-title">
          <Marker>Môn học</Marker>
        </h1>
        {action}
      </div>
      {children}
    </div>
  );
}

/** /subjects while the list loads: the title, no button yet, two grey rows (plan G15). */
export function SubjectsLoading() {
  return (
    <SubjectsFrame>
      <div aria-busy="true" className="flex flex-col gap-4">
        <div className="h-20 rounded-sheet bg-sunken" />
        <div className="h-20 rounded-sheet bg-sunken" />
        <p className="sr-only" role="status">
          Đang tải danh sách môn.
        </p>
      </div>
    </SubjectsFrame>
  );
}
