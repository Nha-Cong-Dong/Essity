import "server-only";

import { loadGraph } from "@/lib/graph-load";
import type { SubjectGraph } from "@/lib/graph-multi";
import { vaultSubjects } from "@/lib/vault-api";

// V16/V17: the graph of every subject (one read each, in parallel); a subject whose graph cannot be
// read is left out rather than breaking the page.
export async function loadAllGraphs(onlySubjectId?: string): Promise<SubjectGraph[]> {
  const subjects = await vaultSubjects();
  const picked = onlySubjectId ? subjects.filter((s) => s.id === onlySubjectId) : subjects;
  const loaded = await Promise.all(
    picked.map(async (s): Promise<SubjectGraph | null> => {
      try {
        return { id: s.id, name: s.name, data: await loadGraph(s.id, null) };
      } catch {
        return null;
      }
    }),
  );
  return loaded.filter((g): g is SubjectGraph => g !== null);
}
