import type { ReactNode } from "react";
import { Suspense } from "react";

import { CommandLive } from "@/components/command-live";
import { isSubjectId } from "@/lib/subject-id";

type Params = Promise<{ id: string }>;

// `params` is request data: read it inside a Suspense so the screens still prerender their shells.
async function Bar({ params }: { params: Params }) {
  const { id } = await params;
  return isSubjectId(id) ? <CommandLive key={id} subjectId={id} /> : null;
}

// T9.3 (US-18): the command bar of every subject screen. The layout only hosts it: each screen keeps
// its own shell (the bar is drawn into the shell's slot) and its own checks of who may see the subject.
export default function SubjectLayout({ children, params }: { children: ReactNode; params: Params }) {
  return (
    <>
      {children}
      <Suspense fallback={null}>
        <Bar params={params} />
      </Suspense>
    </>
  );
}
