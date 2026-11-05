import { redirect } from "next/navigation";

// Q23: the old per-subject graph route. The graph of every subject lives at /graph; this link
// (still on the Today screen) opens it with this subject switched on and the others off.
export default async function SubjectGraphRedirect({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/graph?subject=${encodeURIComponent(id)}`);
}
