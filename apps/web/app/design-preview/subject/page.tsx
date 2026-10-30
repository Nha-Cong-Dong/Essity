import type { Metadata } from "next";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { AppShell } from "@/components/shells";
import { SubjectBlock } from "./block";
import { SUBJECT_FIXTURE, SUBJECT_LONG, SUBJECT_STATES } from "@/lib/fixtures/today-v2";

export const metadata: Metadata = { title: "Design preview: màn môn · Essity" };

// The suggestion block of the subject screen with fixed data (T7.13a, ADR-0025). `?state=` picks
// a case, `?long=1` the long unbroken name. Closed outside development unless WEB_DESIGN_PREVIEW=1.

type Query = Promise<{ state?: string; long?: string }>;

async function Fixture({ searchParams }: { searchParams: Query }) {
  const { state = "suggested", long } = await searchParams;
  const subject = long ? SUBJECT_LONG : SUBJECT_FIXTURE;
  const suggestion = SUBJECT_STATES[state] ?? SUBJECT_STATES.suggested;
  return (
    <AppShell current="/subjects" account={<AccountMenu email="xem-thu@example.com" />}>
      <div className="mx-auto flex w-full max-w-280 flex-col gap-6">
        <a href="/subjects" className="text-small">
          Môn học
        </a>
        <h1 className="m-0 font-display text-title wrap-anywhere">{subject.name}</h1>
        <p className="m-0 text-read text-ink-soft">
          Thi ngày {subject.exam_date} (còn {subject.days} ngày)
        </p>
        <SubjectBlock subjectId={subject.id} subjectName={subject.name} state={suggestion} />
      </div>
    </AppShell>
  );
}

// searchParams is read at request time: under cacheComponents that needs a Suspense around it.
export default function SubjectFixture(props: { searchParams: Query }) {
  return (
    <Suspense>
      <Fixture {...props} />
    </Suspense>
  );
}
