import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { EmptyState } from "@/components/empty-state";
import { AppShell, PageColumn } from "@/components/shells";
import { CardList } from "@/components/vault/card-list";
import { requireVerifiedSession } from "@/lib/session";
import {
  type VaultCard,
  type VaultSession,
  type VaultSubject,
  vaultCards,
  vaultSessions,
  vaultSubjects,
} from "@/lib/vault-api";

export const metadata: Metadata = { title: "Kho kiến thức · Essity" };

// G1: Môn -> Buổi học -> Bộ sưu tập thẻ, one route, the level chosen by ?subject= and ?session=.

type Search = { subject?: string | string[]; session?: string | string[] };
const one = (v: string | string[] | undefined) => (typeof v === "string" ? v : undefined);

async function Account() {
  await connection();
  const me = await requireVerifiedSession();
  return <AccountMenu email={me.email} />;
}

const LINK =
  "block rounded-sheet border border-line border-t-4 border-t-hong p-5 text-ink no-underline hover:bg-rose-50";

type View =
  | { level: "cards"; title: string; cards: VaultCard[] }
  | { level: "sessions"; sessions: VaultSession[] }
  | { level: "subjects"; subjects: VaultSubject[] };

async function load(subjectId?: string, sessionId?: string): Promise<View | null> {
  try {
    if (sessionId) return { level: "cards", ...(await vaultCards(sessionId)) };
    if (subjectId) return { level: "sessions", sessions: await vaultSessions(subjectId) };
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
  if (view === null) return <EmptyState title="Chưa mở được kho kiến thức." hint="Tải lại trang sau ít phút." />;
  if (view.level === "cards") {
    return (
      <>
        <a href={subjectId ? `/kho-kien-thuc?subject=${subjectId}` : "/kho-kien-thuc"} className="text-body text-ink-soft">
          ← Các buổi học
        </a>
        <h1 className="m-0 text-title">{view.title || "Buổi học"}</h1>
        <CardList cards={view.cards} />
      </>
    );
  }
  if (view.level === "sessions") {
    return (
      <>
        <a href="/kho-kien-thuc" className="text-body text-ink-soft">
          ← Các môn
        </a>
        <h1 className="m-0 font-display text-display">Các buổi học</h1>
        {view.sessions.length === 0 ? (
          <EmptyState mascot="cho" title="Môn này chưa có buổi học nào." hint="Ghi một buổi học, thẻ sẽ xuất hiện ở đây." />
        ) : (
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {view.sessions.map((s) => (
              <li key={s.id}>
                <a className={LINK} href={`/kho-kien-thuc?subject=${subjectId}&session=${s.id}`}>
                  <span className="block text-lead font-semibold">{s.title || "Buổi học"}</span>
                  <span className="block text-body text-ink-soft">
                    {s.studied_on ?? ""} · {s.cards} thẻ
                  </span>
                </a>
              </li>
            ))}
          </ul>
        )}
      </>
    );
  }
  return (
    <>
      <h1 className="m-0 font-display text-display">Kho kiến thức</h1>
      {view.subjects.length === 0 ? (
        <EmptyState
          mascot="vui"
          title="Chưa có môn nào."
          hint="Tạo môn và ghi buổi học đầu tiên, các thẻ sẽ được lưu ở đây."
          action={
            <a href="/subjects/new" className="text-body font-semibold">
              Tạo môn
            </a>
          }
        />
      ) : (
        <ul className="m-0 flex list-none flex-col gap-3 p-0">
          {view.subjects.map((s) => (
            <li key={s.id}>
              <a className={LINK} href={`/kho-kien-thuc?subject=${s.id}`}>
                <span className="block text-lead font-semibold">{s.name}</span>
                <span className="block text-body text-ink-soft">
                  {s.sessions} buổi học · {s.cards} thẻ
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </>
  );
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
      <PageColumn width="read" className="flex flex-col gap-4">
        <Suspense fallback={null}>
          <Vault {...props} />
        </Suspense>
      </PageColumn>
    </AppShell>
  );
}
