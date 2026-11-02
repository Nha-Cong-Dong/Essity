// T7.12d (US-02b AC14): the subject's cards grouped by outline section, as core-api answers them.
export type SectionCard = { id: string; title: string; content: string; kind: string; status: string };
export type SectionGroup = { section_id: string | null; section_title: string | null; units: SectionCard[] };

/** The groups, or null when they could not be read (a neutral line, never a throw). */
export async function loadUnitsBySection(subjectId: string, fetchFn: typeof fetch = fetch): Promise<SectionGroup[] | null> {
  try {
    const response = await fetchFn(`/api/subjects/${subjectId}/units/by-section`, { credentials: "same-origin" });
    if (!response.ok) return null;
    const json = (await response.json()) as { groups?: unknown };
    return Array.isArray(json.groups) ? (json.groups as SectionGroup[]) : null;
  } catch {
    return null;
  }
}
