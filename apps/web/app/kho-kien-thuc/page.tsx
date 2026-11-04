import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { EmptyState } from "@/components/empty-state";
import { AppShell, PageColumn } from "@/components/shells";
import { VaultView, type VaultViewData } from "@/components/vault/vault-view";
import type { SubjectGraph } from "@/lib/graph-multi";
import { loadAllGraphs } from "@/lib/graph-multi-load";
import { requireVerifiedSession } from "@/lib/session";
import {
  vaultCards,
  vaultSessions,
  vaultSubjects,
} from "@/lib/vault-api";

export const metadata: Metadata = { title: "Kho kiến thức · Essity" };

// G1: Môn -> Buổi học -> Bộ sưu tập thẻ, one route, the level chosen by ?subject= and ?session=.

type Search = { subject?: string | string[]; session?: string | string[] };
const one = (v: string | string[] | undefined) =>
  typeof v === "string" ? v : undefined;

async function Account() {
  await connection();
  const me = await requireVerifiedSession();
  return <AccountMenu email={me.email} />;
}

type View = VaultViewData;

async function load(
  subjectId?: string,
  sessionId?: string,
): Promise<View | null> {
  try {
    if (sessionId) return { level: "cards", ...(await vaultCards(sessionId)) };
    if (subjectId) {
      const [sessions, graphs] = await Promise.all([
        vaultSessions(subjectId),
        loadAllGraphs(subjectId).catch(() => [] as SubjectGraph[]),
      ]);
      return { level: "sessions", sessions, graphs };
    }
    return { level: "subjects", subjects: await vaultSubjects() };
  } catch {
    return null;
  }
}

async function Vault({ searchParams }: { searchParams: Promise<Search> }) {
  await connection();
  await requireVerifiedSession();
  const { subject, session } = await searchParams;
  const subjectId = one(subject);
  const view = await load(subjectId, one(session));
  if (view === null)
    return (
      <EmptyState
        title="Chưa mở được kho kiến thức."
        hint="Tải lại trang sau ít phút."
      />
    );
  return <VaultView view={view} subjectId={subjectId} />;
}

export default function VaultPage(props: { searchParams: Promise<Search> }) {
  return (
    <AppShell
      current="/kho-kien-thuc"
      account={
        <Suspense fallback={null}>
          <Account />
        </Suspense>
      }
    >
      <PageColumn width="full" className="flex flex-col gap-4">
        <Suspense fallback={null}>
          <Vault {...props} />
        </Suspense>
      </PageColumn>
    </AppShell>
  );
}
