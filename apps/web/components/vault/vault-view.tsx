import { EmptyState } from "@/components/empty-state";
import { KnowledgeGraph } from "@/components/graph/knowledge-graph";
import { NxList, NxRow } from "@/components/ui/nx-list";
import { CardList } from "@/components/vault/card-list";
import type { SubjectGraph } from "@/lib/graph-multi";
import type { VaultCard, VaultSession, VaultSubject } from "@/lib/vault-api";

// G1: the three levels of the Kho kiến thức (môn, buổi học, thẻ) as one view; the page loads, this draws.

export type VaultViewData =
  | { level: "cards"; title: string; cards: VaultCard[] }
  | { level: "sessions"; sessions: VaultSession[]; graphs: SubjectGraph[] }
  | { level: "subjects"; subjects: VaultSubject[] };

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
          <h1 className="m-0 font-display text-title">
            <span className="hl-word">Các buổi học</span>
          </h1>
          {view.sessions.length === 0 ? (
            <EmptyState
              mascot="cho"
              title="Môn này chưa có buổi học nào."
              hint="Ghi một buổi học, thẻ sẽ xuất hiện ở đây."
            />
          ) : (
            <NxList title="Buổi học" hint="Mới nhất trước">
              {view.sessions.map((s, i) => (
                <NxRow
                  key={s.id}
                  lead={i + 1}
                  state={`${s.cards} thẻ`}
                  href={`/kho-kien-thuc?subject=${subjectId}&session=${s.id}`}
                >
                  <span className="block font-semibold wrap-anywhere">{s.title || "Buổi học"}</span>
                  {s.studied_on && <span className="block text-meta text-ink-soft">{s.studied_on}</span>}
                </NxRow>
              ))}
            </NxList>
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
          <span className="hl-word">Kho</span> kiến thức
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
          <NxList title="Môn học">
            {view.subjects.map((s) => (
              <NxRow
                key={s.id}
                lead={[...s.name.trim()][0]?.toLocaleUpperCase("vi") ?? ""}
                state={`${s.cards} thẻ`}
                href={`/kho-kien-thuc?subject=${s.id}`}
              >
                <span className="block font-semibold break-words">{s.name}</span>
                <span className="block text-meta text-ink-soft">{s.sessions} buổi học</span>
              </NxRow>
            ))}
          </NxList>
        </>
      )}
    </div>
  );
}
