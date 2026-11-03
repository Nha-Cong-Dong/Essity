import "server-only";

import { cookies } from "next/headers";

import { coreFetch } from "@/lib/core";
import { SESSION_COOKIE } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";
import { CoreStatusError } from "@/lib/subjects";

// Kho kiến thức (G1): /v1/vault/* read on the server for /kho-kien-thuc. The vault endpoints are
// not in the generated api-client yet, so the calls are plain and the shapes are written here.

export type VaultSubject = { id: string; name: string; sessions: number; cards: number };
export type VaultSession = { id: string; title: string; studied_on: string | null; cards: number };
export type VaultAnchor = {
  id: string;
  source: string;
  document_id: string | null;
  document_name: string | null;
  page_no: number | null;
  quote: string;
};
export type VaultCard = { id: string; title: string; content: string; kind: string; anchors: VaultAnchor[] };
export type VaultCards = { session_id: string; title: string; cards: VaultCard[] };

export async function vaultGet<T>(path: string): Promise<T> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const response = await coreFetch(path, {
    headers: { accept: "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) },
  });
  if (!response.ok) throw new CoreStatusError(path, response.status);
  return (await response.json()) as T;
}

export const vaultSubjects = () => vaultGet<VaultSubject[]>("/v1/vault/subjects");

export async function vaultSessions(subjectId: string) {
  if (!isSubjectId(subjectId)) throw new CoreStatusError("/v1/vault/subjects/{id}/sessions", 404);
  return vaultGet<VaultSession[]>(`/v1/vault/subjects/${subjectId}/sessions`);
}

export async function vaultCards(sessionId: string) {
  if (!isSubjectId(sessionId)) throw new CoreStatusError("/v1/vault/sessions/{id}/cards", 404);
  return vaultGet<VaultCards>(`/v1/vault/sessions/${sessionId}/cards`);
}
