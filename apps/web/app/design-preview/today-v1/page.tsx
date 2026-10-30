import type { Metadata } from "next";

import { AccountMenu } from "@/components/account-menu";
import { AppShell } from "@/components/shells";
import { TodayScreen } from "@/components/today/today-screen";
import type { Today } from "@/lib/today";

export const metadata: Metadata = { title: "Design preview: hôm nay (v1) · Essity" };

// /today with fixed data, for the layout test (ADR-0025, T2.14): the real shell and TodayScreen,
// no core-api call and no session. Closed outside development unless WEB_DESIGN_PREVIEW=1
// (proxy.ts, lib/design-preview.ts). The busiest state: a session, a backlog note, a long name.

const LONG_WORD = "Kiếntrúcmáytínhvàhệđiềuhànhnângcaohọckỳhainămhaingànhaimươisáu" + "_kếtthúc";

const TODAY: Today = {
  learning_day: "2026-10-21",
  state: "ready",
  session: {
    question_count: 20,
    minutes: 30,
    subjects: [
      { id: "0b8f1d2e-0000-4000-8000-000000000001", name: "Mạng máy tính" },
      { id: "0b8f1d2e-0000-4000-8000-000000000002", name: LONG_WORD },
    ],
  },
  in_progress: null,
  backlog: {
    subject_id: "0b8f1d2e-0000-4000-8000-000000000001",
    subject_name: "Mạng máy tính",
    sessions: 16,
    days: 10,
  },
  next_day: null,
  subjects: [
    { id: "0b8f1d2e-0000-4000-8000-000000000001", name: "Mạng máy tính", exam_date: "2026-12-04", days_until_exam: 40 },
    { id: "0b8f1d2e-0000-4000-8000-000000000002", name: LONG_WORD, exam_date: "2027-01-15", days_until_exam: 82 },
  ],
};

export default function TodayLayoutFixture() {
  return (
    <AppShell current="/today" account={<AccountMenu email="xem-thu@example.com" />}>
      <div className="mx-auto w-full max-w-280">
        <TodayScreen today={TODAY} />
      </div>
    </AppShell>
  );
}
