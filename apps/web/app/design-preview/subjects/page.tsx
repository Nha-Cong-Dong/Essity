import type { Metadata } from "next";

import { AccountMenu } from "@/components/account-menu";
import { AppShell } from "@/components/shells";
import { type ListedSubject, SubjectList } from "@/components/subjects/subject-list";
import { SubjectsFrame } from "@/components/subjects/subjects-frame";

export const metadata: Metadata = { title: "Design preview: môn học · Essity" };

// The /subjects screen with fixed data, for the layout test (ADR-0025, T2.3c plan G4): the real
// shell, frame and SubjectList, no core-api call and no session. Closed outside development unless
// WEB_DESIGN_PREVIEW=1 (proxy.ts, lib/design-preview.ts). Dates are fixed strings, not today's.

// A word with no space, as a user may type one (CSDL_nâng_cao_…): it must wrap, never spill.
const LONG_WORD = "Kiếntrúcmáytínhvàhệđiềuhànhnângcaohọckỳhainămhaingànhaimươisáu".repeat(2) + "_kếtthúc";

const SUBJECTS: ListedSubject[] = [
  { id: "0b8f1d2e-0000-4000-8000-000000000001", name: "Mạng máy tính", exam_date: "2026-12-04", days_until_exam: 40, has_history: false },
  {
    id: "0b8f1d2e-0000-4000-8000-000000000002",
    name: "Cơ sở dữ liệu nâng cao và tối ưu truy vấn cho hệ thống lớn",
    exam_date: "2027-01-03",
    days_until_exam: 70,
    has_history: false,
  },
  { id: "0b8f1d2e-0000-4000-8000-000000000003", name: LONG_WORD, exam_date: "2026-11-24", days_until_exam: 30, has_history: true },
  { id: "0b8f1d2e-0000-4000-8000-000000000004", name: "Hệ điều hành", exam_date: "2027-10-25", days_until_exam: 365, has_history: false },
  { id: "0b8f1d2e-0000-4000-8000-000000000005", name: "Xác suất thống kê", exam_date: "2026-10-26", days_until_exam: 1, has_history: false },
  { id: "0b8f1d2e-0000-4000-8000-000000000006", name: "Toán rời rạc", exam_date: "2026-10-25", days_until_exam: 0, has_history: false },
];

export default function SubjectsLayoutFixture() {
  return (
    <AppShell current="/subjects" account={<AccountMenu email="xem-thu@example.com" />}>
      <SubjectsFrame>
        <SubjectList subjects={SUBJECTS} example="15/12/2026" />
      </SubjectsFrame>
    </AppShell>
  );
}
