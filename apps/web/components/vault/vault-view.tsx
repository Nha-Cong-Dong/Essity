import { ArrowRight } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
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
  | { level: "subjects"; subjects: VaultViewSubject[] };

/** A vault subject with its newest sessions (the page loads them; absent when they did not load). */
export type VaultViewSubject = VaultSubject & { recent?: { title: string; studied_on: string | null }[] };

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

function shortDate(value: string | null): string | null {
  const d = dayParts(value);
  return d ? `${d.day}/${d.month.padStart(2, "0")}` : null;
}

/** The plum field of the subjects level (mockups vault.html): the number left, "Mới thêm" right. */
function SubjectsField({ cards, meta, subjects }: { cards: number; meta: string; subjects: VaultViewSubject[] }) {
  const recent = subjects
    .flatMap((s) => (s.recent ?? []).map((r) => ({ ...r, subject: s.name })))
    .filter((r) => r.title)
    .sort((a, b) => (b.studied_on ?? "").localeCompare(a.studied_on ?? ""))
    .slice(0, 3);
  return (
    <Block
      as="section"
      tier="field"
      aria-label="Tóm tắt"
      data-vault-sub
      className={recent.length > 0 ? "grid gap-6 min-[901px]:grid-cols-2 min-[901px]:gap-10" : "flex flex-col gap-1"}
    >
      <div className="flex flex-col justify-center gap-1">
        <p className="m-0 flex items-baseline gap-3">
          <span className="font-display text-display tabular-nums" data-vault-total>
            {cards}
          </span>
          <span className="text-lead font-semibold">thẻ trong kho</span>
        </p>
        <p className="m-0 text-body text-on-plum-soft">{meta}</p>
      </div>
      {recent.length > 0 && (
        <div className="flex min-w-0 flex-col gap-1 min-[901px]:border-l min-[901px]:border-on-plum-soft/30 min-[901px]:pl-10">
          <p className="m-0 text-meta font-semibold text-on-plum-soft">Mới thêm</p>
          <ul className="m-0 flex list-none flex-col p-0">
            {recent.map((r, i) => (
              <li key={`${r.title}-${i}`} className="flex flex-wrap items-baseline justify-between gap-x-4 border-t border-on-plum-soft/20 py-3 first:border-t-0">
                <span className="font-display text-lead wrap-anywhere">{r.title}</span>
                <span className="text-meta text-on-plum-soft">
                  {[r.subject, shortDate(r.studied_on)].filter(Boolean).join(" · ")}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Block>
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
      <h1 className="m-0 font-display text-title">Kho kiến thức</h1>
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
          <SubjectsField cards={totalCards} meta={`${totalSessions} buổi học · ${subjects.length} môn`} subjects={subjects} />
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
                      {s.recent && s.recent.some((r) => r.title) ? (
                        <span className="mt-2 flex flex-wrap gap-2">
                          {s.recent
                            .filter((r) => r.title)
                            .map((r, i) => (
                              <span key={`${r.title}-${i}`} className="rounded-full bg-hong-tint px-3 py-1 text-meta font-medium text-ink">
                                {r.title}
                              </span>
                            ))}
                        </span>
                      ) : null}
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
