import type { Metadata } from "next";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { AppShell } from "@/components/shells";
import { SyllabusScreen } from "@/components/syllabus/syllabus-screen";
import { UploadScreen } from "@/components/syllabus/upload-files";
import { SYLLABUS_STATE_IDS, UPLOAD_STATE_IDS } from "@/lib/fixtures/syllabus";

export const metadata: Metadata = { title: "Design preview: đề cương · Essity" };

// The Đề cương screen and the role picker of the upload form (T7.5a) with fixed data and no
// core-api. `?state=` picks a state (default: ready; `upload-*` shows the upload form). The live
// routes are not touched. Closed outside development unless WEB_DESIGN_PREVIEW=1 (proxy.ts).

async function Fixture({ searchParams }: { searchParams: Promise<{ state?: string }> }) {
  const { state = "ready" } = await searchParams;
  const upload = UPLOAD_STATE_IDS.find((id) => id === state);
  const known = SYLLABUS_STATE_IDS.find((id) => id === state) ?? "ready";
  return (
    <AppShell current="/today" account={<AccountMenu email="xem-thu@example.com" />}>
      <div className="mx-auto w-full max-w-(--col-session)">
        {upload ? <UploadScreen key={upload} state={upload} /> : <SyllabusScreen key={known} state={known} />}
      </div>
    </AppShell>
  );
}

// searchParams is read at request time: under cacheComponents that needs a Suspense around it.
export default function SyllabusFixture(props: { searchParams: Promise<{ state?: string }> }) {
  return (
    <Suspense>
      <Fixture {...props} />
    </Suspense>
  );
}
