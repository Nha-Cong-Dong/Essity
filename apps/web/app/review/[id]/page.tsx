import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { ReviewScreen } from "@/components/review/review-screen";
import { requireVerifiedSession } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";

export const metadata: Metadata = { title: "Ôn tập · Essity" };

// T2.15, T2.16 (US-04, US-05, DESIGN.md §6.4, §6.5): a review session, one question at a time.
// The screen reads the session through web's routes, which check it is this user's; an id that is
// not a UUID is the not-found page without a call.
async function Review({ params }: { params: Promise<{ id: string }> }) {
  await connection();
  await requireVerifiedSession();
  const { id } = await params;
  if (!isSubjectId(id)) notFound();
  return <ReviewScreen sessionId={id} />;
}

export default function ReviewPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <Suspense fallback={<div aria-busy="true" className="min-h-full" />}>
      <Review params={params} />
    </Suspense>
  );
}
