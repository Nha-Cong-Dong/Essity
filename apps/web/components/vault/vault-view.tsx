import { ArrowRight } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { HeadMascot } from "@/components/head-mascot";
import { BackLink, Block } from "@/components/screen-kit";
import { Button } from "@/components/ui/button";
import { CardList } from "@/components/vault/card-list";
import type { VaultCard, VaultSession, VaultSubject } from "@/lib/vault-api";

// V4-SCREENS-B (design-v4 mockups vault, vault-subject, vault-session): the three levels of the Kho
// kiến thức (môn, buổi học, thẻ). Each level opens with one plum field (T1: the number of cards),
// then one white sheet of full-row links; the cards of a session are a horizontal band on a plum
// stage (CardList). The page loads, this draws.

export type VaultViewData =
  | { level: "cards"; title: string; cards: VaultCard[]; subjectName?: string }
  | { level: "sessions"; sessions: VaultSession[]; subjectName?: string }
  | { level: "subjects"; subjects: VaultSubject[] };

/** "04/11/2026" or "2026-11-04" -> { day: "04", month: "11" }; anything else is shown as it is. */
function dayParts(value: string | null): { day: string; month: string } | null {
  if (!value) return null;
  const dmy = /^(\d{1,2})\/(\d{1,2})\/\d{4}$/.exec(value);
  if (dmy) return { day: dmy[1].padStart(2, "0"), month: dmy[2] };
  const ymd = /^\d{4}-(\d{2})-(\d{2})/.exec(value);
  if (ymd) return { day: ymd[2], month: String(Number(ymd[1])) };
  return null;
}

const ROW =
  "grid grid-cols-[44px_minmax(0,1fr)] items-center gap-3.5 rounded-row p-3 no-underline text-ink hover:bg-sunken min-[641px]:grid-cols-[52px_minmax(0,1fr)_auto] min-[641px]:gap-4.5 min-[641px]:px-5 min-[641px]:py-4";

function Go({ label }: { label: string }) {
  return (
    <span aria-hidden="true" className="hidden items-center gap-2 text-meta whitespace-nowrap text-ink-soft min-[641px]:inline-flex">
      {label}
      <ArrowRight className="size-5" />
    </span>
  );
}

/** The plum field every level opens with: the number of cards, once, and a line under it. */
function Field({ cards, meta, label = "thẻ" }: { cards: number; meta: string; label?: string }) {
  return (
    <Block as="section" tier="field" aria-label="Tóm tắt" className="flex flex-col gap-1" data-vault-sub>
      <p className="m-0 flex items-baseline gap-3">
        <span className="font-display text-display tabular-nums" data-vault-total>
          {cards}
        </span>
        <span className="text-lead font-semibold">{label}</span>
      </p>
      <p className="m-0 text-body text-on-plum-soft">{meta}</p>
    </Block>
  );
}

export function VaultView({ view, subjectId }: { view: VaultViewData; subjectId?: string }) {
  if (view.level === "cards") {
    return (
      <div className="flex min-w-0 flex-col gap-4">
        <BackLink href={subjectId ? `/kho-kien-thuc?subject=${subjectId}` : "/kho-kien-thuc"}>Quay lại</BackLink>
        <div className="max-w-160">
          <h1 className="m-0 text-title wrap-anywhere">{view.title || "Buổi học"}</h1>
        </div>
        <CardList cards={view.cards} subjectName={view.subjectName} />
      </div>
    );
  }
  if (view.level === "sessions") {
    const cards = view.sessions.reduce((n, s) => n + s.cards, 0);
    return (
      <div className="flex min-w-0 flex-col gap-5">
        <header className="flex flex-col gap-2">
          <BackLink href="/kho-kien-thuc">Quay lại</BackLink>
          <h1 className="m-0 text-title wrap-anywhere">{view.subjectName || "Các buổi học"}</h1>
        </header>
        {view.sessions.length === 0 ? (
          <Block as="section" tier="sheet" aria-label="Chưa có buổi học">
            <EmptyState
              mascot="rong"
              title="Môn này chưa có buổi học nào."
              hint="Ghi một buổi học, thẻ sẽ xuất hiện ở đây."
              action={
                subjectId ? (
                  <Button render={<a href={`/subjects/${subjectId}/sessions/study`} />} nativeButton={false}>
                    Bắt đầu buổi học
                  </Button>
                ) : undefined
              }
            />
          </Block>
        ) : (
          <>
            <Field cards={cards} meta={`${view.sessions.length} buổi học`} />
            <Block as="section" tier="sheet" aria-label="Các buổi học" className="p-2 min-[901px]:p-2">
              <ul className="m-0 flex list-none flex-col p-0">
                {view.sessions.map((s) => {
                  const when = dayParts(s.studied_on);
                  return (
                    <li key={s.id} className="border-t border-line first:border-t-0">
                      <a href={`/kho-kien-thuc?subject=${subjectId}&session=${s.id}`} className={ROW}>
                        <span
                          aria-hidden="true"
                          className="grid size-11 place-items-center rounded-control bg-hong-tint leading-none min-[641px]:size-13"
                        >
                          {when ? (
                            <span className="flex flex-col items-center">
                              <b className="font-display text-lead">{when.day}</b>
                              <span className="text-meta text-ink-soft">Th{when.month}</span>
                            </span>
                          ) : (
                            <span className="font-display text-lead">·</span>
                          )}
                        </span>
                        <span className="flex min-w-0 flex-col">
                          <span className="font-display text-lead wrap-anywhere">{s.title || "Buổi học"}</span>
                          <span className="text-meta text-ink-soft">
                            {[when ? null : s.studied_on, `${s.cards} thẻ`].filter(Boolean).join(" · ")}
                          </span>
                        </span>
                        <Go label="Mở buổi" />
                      </a>
                    </li>
                  );
                })}
              </ul>
            </Block>
          </>
        )}
      </div>
    );
  }
  const subjects = view.subjects;
  const totalCards = subjects.reduce((n, s) => n + s.cards, 0);
  const totalSessions = subjects.reduce((n, s) => n + s.sessions, 0);
  return (
    <div className="flex min-w-0 flex-col gap-5">
      <div className="flex items-center justify-between gap-3">
        <h1 className="m-0 font-display text-title">Kho kiến thức</h1>
        <HeadMascot pose="rong" />
      </div>
      {subjects.length === 0 ? (
        <Block as="section" tier="sheet" aria-label="Chưa có môn">
          <EmptyState
            mascot="rong"
            title="Chưa có môn nào."
            hint="Tạo môn và ghi buổi học đầu tiên, các thẻ sẽ được lưu ở đây."
            action={
              <Button render={<a href="/subjects/new" />} nativeButton={false}>
                Tạo môn
              </Button>
            }
          />
        </Block>
      ) : (
        <>
          <Field cards={totalCards} meta={`${totalSessions} buổi học · ${subjects.length} môn`} label="thẻ trong kho" />
          <Block as="section" tier="sheet" aria-label="Các môn" className="p-2 min-[901px]:p-2" data-vault-subjects>
            <ul className="m-0 flex list-none flex-col p-0">
              {subjects.map((s) => (
                <li key={s.id} className="border-t border-line first:border-t-0">
                  <a href={`/kho-kien-thuc?subject=${s.id}`} className={ROW}>
                    <span
                      aria-hidden="true"
                      className="grid size-11 place-items-center rounded-control bg-hong-tint font-display text-lead text-hong-text min-[641px]:size-13"
                    >
                      {s.name.trim().charAt(0).toUpperCase()}
                    </span>
                    <span className="flex min-w-0 flex-col">
                      <span className="font-display text-lead wrap-anywhere">{s.name}</span>
                      <span className="text-meta text-ink-soft">
                        <span data-vault-cards>{s.cards}</span> thẻ · {s.sessions} buổi học
                      </span>
                    </span>
                    <Go label="Mở môn" />
                  </a>
                </li>
              ))}
            </ul>
          </Block>
        </>
      )}
    </div>
  );
}
