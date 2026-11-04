import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountMenu } from "@/components/account-menu";
import { NoteSticker } from "@/components/motifs";
import { StatBig } from "@/components/screen-kit";
import { EmptyState } from "@/components/empty-state";
import { AppShell, PageColumn } from "@/components/shells";
import { KnowledgeGraph } from "@/components/graph/knowledge-graph";
import { CardList } from "@/components/vault/card-list";
import type { SubjectGraph } from "@/lib/graph-multi";
import { loadAllGraphs } from "@/lib/graph-multi-load";
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
const one = (v: string | string[] | undefined) =>
  typeof v === "string" ? v : undefined;

async function Account() {
  await connection();
  const me = await requireVerifiedSession();
  return <AccountMenu email={me.email} />;
}

const LINK =
  "relative block rounded-sheet bg-sheet p-5 text-ink no-underline shadow-sheet hover:bg-rose-50";

type View =
  | { level: "cards"; title: string; cards: VaultCard[] }
  | { level: "sessions"; sessions: VaultSession[]; graphs: SubjectGraph[] }
  | { level: "subjects"; subjects: VaultSubject[] };

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
  if (view.level === "cards") {
    return (
      <div className="flex min-w-0 flex-col gap-4">
        <a
          href={
            subjectId ? `/kho-kien-thuc?subject=${subjectId}` : "/kho-kien-thuc"
          }
          className="text-body text-ink-soft"
        >
          ← Các buổi học
        </a>
        <div className="relative max-w-160 pr-24">
          <h1 className="m-0 text-title wrap-anywhere">{view.title || "Buổi học"}</h1>
          {view.cards.length > 0 && <NoteSticker className="top-0 right-0">{view.cards.length} thẻ</NoteSticker>}
        </div>
        <CardList cards={view.cards} />
      </div>
    );
  }
  if (view.level === "sessions") {
    return (
      <div className="grid min-w-0 gap-8 lg:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-4">
          <a href="/kho-kien-thuc" className="text-body text-ink-soft">
            ← Các môn
          </a>
          <h1 className="m-0 font-display text-display">Các <span className="px-1" style={{ backgroundImage: "linear-gradient(to top, var(--hl-band) 35%, transparent 35%)" }}>buổi học</span></h1>
          {view.sessions.length === 0 ? (
            <EmptyState
              mascot="cho"
              title="Môn này chưa có buổi học nào."
              hint="Ghi một buổi học, thẻ sẽ xuất hiện ở đây."
            />
          ) : (
            <ul className="m-0 grid list-none gap-4 p-0 [grid-template-columns:repeat(auto-fill,minmax(min(100%,220px),1fr))]">
              {view.sessions.map((s) => (
                <li key={s.id}>
                  <a
                    className={LINK}
                    href={`/kho-kien-thuc?subject=${subjectId}&session=${s.id}`}
                  >
                    <span className="block text-lead font-semibold">
                      {s.title || "Buổi học"}
                    </span>
                    <span className="block text-body text-ink-soft">
                      {s.studied_on ?? ""} · {s.cards} thẻ
                    </span>
                  </a>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <h2 className="m-0 font-display text-lead">Đồ thị tri thức</h2>
          <KnowledgeGraph graphs={view.graphs} height="55vh" />
        </div>
      </div>
    );
  }
  const totalCards = view.subjects.reduce((n, s) => n + s.cards, 0);
  const totalSessions = view.subjects.reduce((n, s) => n + s.sessions, 0);
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <h1 className="m-0 font-display text-display"><span className="px-1" style={{ backgroundImage: "linear-gradient(to top, var(--hl-band) 35%, transparent 35%)" }}>Kho</span> kiến thức</h1>
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
        <>
          <div className="grid gap-4 min-[901px]:grid-cols-12">
            <div data-surface="hong" className="relative rounded-tile p-8 min-[901px]:col-span-7">
              <StatBig value={totalCards} label="thẻ trong kho" hint={`${totalSessions} buổi học, ${view.subjects.length} môn`} size="mega" />
            </div>
            <div className="flex flex-col justify-center gap-2 rounded-tile bg-rose-100 p-8 min-[901px]:col-span-5">
              <p className="m-0 font-display text-lead">Mở một môn để xem từng buổi học</p>
              <p className="m-0 text-body text-ink-soft">Mỗi buổi là một ngăn, thẻ nằm trong đó như bưu thiếp.</p>
            </div>
          </div>
          <ul className="m-0 grid list-none gap-4 p-0 [grid-template-columns:repeat(auto-fill,minmax(min(100%,240px),1fr))]">
            {view.subjects.map((s) => (
              <li key={s.id}>
                <a className={LINK} href={`/kho-kien-thuc?subject=${s.id}`}>
                  <span className="block text-lead font-semibold wrap-anywhere">{s.name}</span>
                  <span className="block text-body text-ink-soft">
                    {s.sessions} buổi học · {s.cards} thẻ
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
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
      <PageColumn width="full" className="flex flex-col gap-4">
        <Suspense fallback={null}>
          <Vault {...props} />
        </Suspense>
      </PageColumn>
    </AppShell>
  );
}
