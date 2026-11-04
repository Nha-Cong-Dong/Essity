import type { Metadata } from "next";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { AppShell } from "@/components/shells";
import { SubjectView } from "@/components/subjects/subject-view";
import { FIXTURES } from "@/lib/fixtures/syllabus";
import { SUBJECT_FIXTURE, SUBJECT_STATES } from "@/lib/fixtures/today-v2";
import { entryRow } from "@/lib/subject-entries";

export const metadata: Metadata = { title: "Design preview: màn một môn đầy đủ · Essity" };

// The whole one-subject screen (SubjectView) with fixed data and no core-api, so the page can be
// seen as the learner sees it. Closed outside development unless WEB_DESIGN_PREVIEW=1 (proxy.ts).

const STATS = {
  id: SUBJECT_FIXTURE.id,
  name: SUBJECT_FIXTURE.name,
  examOn: "2026-12-15",
  daysLeft: 46,
  syllabus: { studied: 3, leaves: 93, pagesDone: 40, pages: 820 },
  bank: [{ type: "mcq", ready: 5, practiced: 2, mastered: 1 }],
  retention: 0.9,
  skippedCards: 0,
};

async function Fixture() {
  const nodes = FIXTURES.ready.nodes;
  const entries = entryRow(SUBJECT_FIXTURE.id, { outline: null, questions: { ready: 5, total: 9 }, graphCards: null });
  return (
    <AppShell current="/subjects" account={<AccountMenu email="xem-thu@example.com" />}>
      <SubjectView
        subject={{ ...SUBJECT_FIXTURE, exam_date: "2026-12-15", days_until_exam: 46 }}
        prog={{ done: 3, total: 93 }}
        state={SUBJECT_STATES.suggested}
        nothingDue={false}
        dueCards={[
          { id: "c1", why: "Đến hạn ôn", kind: "card", front: "Cửa sổ trượt trong TCP dùng để làm gì?", back: "Giới hạn số gói gửi mà chưa cần ACK." },
          { id: "c2", why: "Đến hạn ôn", kind: "card", front: "UDP khác TCP ở điểm nào?", back: "Không kết nối, không đảm bảo thứ tự." },
        ]}
        questions={{ total: 9, ready: 5, due_today: 2 }}
        stats={STATS}
        rowEntries={entries.filter((e) => e.key !== "syllabus" && e.key !== "stats" && e.key !== "practice" && e.key !== "graph")}
        nodes={nodes}
      />
    </AppShell>
  );
}

export default function SubjectViewPreview() {
  return (
    <Suspense>
      <Fixture />
    </Suspense>
  );
}
