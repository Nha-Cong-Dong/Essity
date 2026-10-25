import type { ReactNode } from "react";

import { Marker } from "@/components/notebook";

/**
 * The /subjects column and its title (DESIGN.md §6.8), shared by the page and its layout fixture
 * (/design-preview/subjects, T2.3c plan G4): the "Tạo môn" button is pulled up beside the h1
 * (-mt-16), so a fixture without this frame would measure a different layout.
 */
export function SubjectsFrame({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-220 flex-col">
      <h1 className="m-0 mb-8 font-display text-title">
        <Marker>Môn học</Marker>
      </h1>
      {children}
    </div>
  );
}
