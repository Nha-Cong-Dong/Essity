import { EmptyState } from "@/components/empty-state";
import { KnowledgeGraph } from "@/components/graph/knowledge-graph";
import { CardList } from "@/components/vault/card-list";
import type { SubjectGraph } from "@/lib/graph-multi";
import type { VaultCard, VaultSession, VaultSubject } from "@/lib/vault-api";

// G1: the three levels of the Kho kiến thức (môn, buổi học, thẻ) as one view; the page loads, this draws.

export type VaultViewData =
  | { level: "cards"; title: string; cards: VaultCard[] }
  | { level: "sessions"; sessions: VaultSession[]; graphs: SubjectGraph[] }
  | { level: "subjects"; subjects: VaultSubject[] };

const LINK =
  "relative block rounded-tile border border-line bg-sheet p-5 text-ink no-underline hover:bg-sunken";

export function VaultView({ view, subjectId }: { view: VaultViewData; subjectId?: string }) {
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
        <div className="max-w-160">
          <h1 className="m-0 text-title wrap-anywhere">{view.title || "Buổi học"}</h1>
          {view.cards.length > 0 && <p className="m-0 mt-1 text-read text-ink-soft">{view.cards.length} thẻ</p>}
        </div>
        <CardList cards={view.cards} />
      </div>
    );
  }
  if (view.level === "sessions") {
    return (
      <div className="grid min-w-0 gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <a href="/kho-kien-thuc" className="text-body text-ink-soft">
            ← Các môn
          </a>
          <h1 className="m-0 font-display text-title">Các buổi học</h1>
          {view.sessions.length === 0 ? (
            <EmptyState
              mascot="cho"
              title="Môn này chưa có buổi học nào."
              hint="Ghi một buổi học, thẻ sẽ xuất hiện ở đây."
            />
          ) : (
            <ul className="m-0 flex list-none flex-col rounded-tile border border-line bg-sheet px-5 py-1" data-sessions>
              {view.sessions.map((s) => (
                <li key={s.id} className="border-t border-line first:border-t-0">
                  <a
                    className="flex min-h-16 flex-wrap items-center justify-between gap-x-4 gap-y-1 py-3 hover:bg-sunken"
                    href={`/kho-kien-thuc?subject=${subjectId}&session=${s.id}`}
                  >
                    <span className="min-w-0 flex-1 basis-48">
                      <span className="block font-semibold wrap-anywhere">{s.title || "Buổi học"}</span>
                      {s.studied_on && <span className="block text-meta text-ink-soft">{s.studied_on}</span>}
                    </span>
                    <span className="rounded-full bg-sunken px-3 py-0.5 text-meta">{s.cards} thẻ</span>
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
      <div>
        <h1 className="m-0 font-display text-title">
          <span className="px-1" style={{ backgroundImage: "linear-gradient(to top, var(--hl-band) 35%, transparent 35%)" }}>Kho</span> kiến thức
        </h1>
        {view.subjects.length > 0 && (
          <p className="m-0 mt-1 text-read text-ink-soft" data-vault-sub>
            {totalCards} thẻ · {totalSessions} buổi học · {view.subjects.length} môn
          </p>
        )}
      </div>
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
          <ul className="m-0 grid list-none gap-4 p-0 [grid-template-columns:repeat(auto-fill,minmax(min(100%,280px),1fr))]">
            {view.subjects.map((s) => (
              <li key={s.id}>
                <a className={`${LINK} flex h-full flex-col gap-1`} href={`/kho-kien-thuc?subject=${s.id}`}>
                  <span className="block font-semibold break-words">{s.name}</span>
                  <span className="block text-meta text-ink-soft">{s.sessions} buổi học</span>
                  <span className="mt-2 block text-meta">{s.cards} thẻ</span>
                </a>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
