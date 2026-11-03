import "server-only";

import { cookies } from "next/headers";

import type { CardSources } from "@/lib/card-source";
import { coreFetch } from "@/lib/core";
import { SESSION_COOKIE } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";
import { CoreStatusError } from "@/lib/subjects";

/** Throws CoreStatusError (404 = not theirs, or not a UUID). */
export async function loadCardSources(cardId: string): Promise<CardSources> {
  if (!isSubjectId(cardId)) throw new CoreStatusError("/v1/units/{id}/sources", 404);
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const response = await coreFetch(`/v1/units/${cardId}/sources`, {
    headers: { accept: "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) },
  });
  if (!response.ok) throw new CoreStatusError("/v1/units/{id}/sources", response.status);
  return (await response.json()) as CardSources;
}
