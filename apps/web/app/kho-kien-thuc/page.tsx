import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { EmptyState } from "@/components/empty-state";
import { AppShell, PageColumn } from "@/components/shells";
import { VaultView, type VaultViewData } from "@/components/vault/vault-view";
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

/** The subject's name for the headings; the page still draws without it. */
async function nameOf(subjectId?: string): Promise<string | undefined> {
  if (!subjectId) return undefined;
  try {
    return (await vaultSubjects()).find((s) => s.id === subjectId)?.name;
  } catch {
    return undefined;
  }
}

async function load(
  subjectId?: string,
  sessionId?: string,
): Promise<View | null> {
  try {
    if (sessionId) {
      const [cards, subjectName] = await Promise.all([vaultCards(sessionId), nameOf(subjectId)]);
      return { level: "cards", ...cards, subjectName };
    }
    if (subjectId) {
      const [sessions, subjectName] = await Promise.all([vaultSessions(subjectId), nameOf(subjectId)]);
      return { level: "sessions", sessions, subjectName };
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
      <PageColumn width="wide" className="flex flex-col gap-4">
        <Suspense fallback={null}>
          <Vault {...props} />
        </Suspense>
      </PageColumn>
    </AppShell>
  );
}
