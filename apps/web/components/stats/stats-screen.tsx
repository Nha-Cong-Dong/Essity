"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef } from "react";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Sheet } from "@/components/ui/sheet";
import { statsFixture, type StatsState, type SubjectStats } from "@/lib/fixtures/stats";
import { buildGrid, daysLeftText, percentOf } from "@/lib/stats";

import { ActivityGrid } from "./activity-grid";
import { MiniNotebook, StatTile } from "./stat-tile";

// T9.5a (US-10 AC1-AC7, AC10; DESIGN §6.13, .work/T9.5a/design-decisions.md): the Thống kê screen
// from typed fixtures, no API. A read-only screen: the normal state has no primary button. A
// primary appears only where there is nothing to read (error, nothing yet, or a scope with no day
// recorded): at most one per state. No verdict, no ranking, no comparison anywhere.

const ALL = "";

function examLine(s: SubjectStats): string {
  if (s.examOn === null || s.daysLeft === null) return "Chưa đặt ngày thi";
  const [y, m, d] = s.examOn.split("-");
  const date = `${Number(d)}/${Number(m)}/${y}`;
  return s.daysLeft < 0 ? `Thi ${date} · đã qua` : `Thi ${date} · ${daysLeftText(s.daysLeft)}`;
}

function Skeleton() {
  return (
    <div aria-busy="true" aria-label="Đang tải thống kê" className="mt-6 flex flex-col gap-4">
      {[0, 1].map((i) => (
        <div key={i} className="h-40 rounded-sheet bg-sunken motion-safe:animate-pulse" aria-hidden="true" />
      ))}
      <div className="h-64 rounded-sheet bg-sunken motion-safe:animate-pulse" aria-hidden="true" />
    </div>
  );
}

function BankTile({ s, open }: { s: SubjectStats; open: boolean }) {
  if (s.bank === null) {
    return (
      <StatTile
        label="Bộ câu hỏi"
        value="Chưa có bộ câu hỏi."
        note={
          <a href="#" className="underline">
            Tải bộ câu hỏi
          </a>
        }
      />
    );
  }
  const ready = s.bank.reduce((n, t) => n + t.ready, 0);
  const practiced = s.bank.reduce((n, t) => n + t.practiced, 0);
  const mastered = s.bank.reduce((n, t) => n + t.mastered, 0);
  return (
    <StatTile
      label="Bộ câu hỏi"
      value={`Đã thuộc ${mastered} / ${ready} câu sẵn sàng`}
      note={`${practiced} câu đã luyện`}
      percent={percentOf(mastered, ready)}
    >
      <details open={open} className="mt-1">
        <summary className="flex min-h-11 cursor-pointer items-center text-meta underline decoration-line-strong decoration-[1.5px] underline-offset-[5px]">
          Theo dạng câu
        </summary>
        <table className="w-full [border-collapse:collapse] text-meta">
          <thead>
            <tr>
              <th scope="col" className="py-1 pr-2 text-left font-semibold">
                Dạng câu
              </th>
              <th scope="col" className="py-1 pr-2 text-end font-semibold">
                Sẵn sàng
              </th>
              <th scope="col" className="py-1 pr-2 text-end font-semibold">
                Đã luyện
              </th>
              <th scope="col" className="py-1 text-end font-semibold">
                Đã thuộc
              </th>
            </tr>
          </thead>
          <tbody>
            {s.bank.map((t) => (
              <tr key={t.type} className="border-t border-line">
                <th scope="row" data-user className="py-1 pr-2 text-left font-normal wrap-anywhere">
                  {t.type}
                </th>
                <td className="py-1 pr-2 text-end tabular-nums">{t.ready}</td>
                <td className="py-1 pr-2 text-end tabular-nums">{t.practiced}</td>
                <td className="py-1 text-end tabular-nums">{t.mastered}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </StatTile>
  );
}

function SubjectBlock({ s, open }: { s: SubjectStats; open: boolean }) {
  const { studied, leaves, pagesDone, pages } = s.syllabus;
  return (
    <Sheet data-subject-block={s.id} className="@container">
      <div className="flex items-start gap-4">
        <MiniNotebook />
        <div className="min-w-0">
          <h2 data-user className="m-0 text-read font-semibold wrap-anywhere">
            {s.name}
          </h2>
          <p className="m-0 text-meta text-ink-soft">
            {examLine(s)}
            {s.skippedCards > 0 && ` · Đã bỏ qua ${s.skippedCards} thẻ`}
          </p>
        </div>
      </div>
      <div className="mt-6 grid grid-cols-1 gap-6 @min-[600px]:grid-cols-3">
        {leaves === 0 ? (
          <StatTile label="Đề cương đã học" value="Chưa có đề cương để tính." />
        ) : (
          <StatTile
            label="Đề cương đã học"
            value={`${studied}/${leaves} mục`}
            note={`${pagesDone}/${pages} trang`}
            percent={percentOf(studied, leaves)}
          />
        )}
        <BankTile s={s} open={open} />
        {s.retention === null ? (
          <StatTile label="Độ vững nhớ" value="Chưa có thẻ để tính." />
        ) : (
          <StatTile
            label="Độ vững nhớ"
            value={`${Math.round(s.retention * 100)}%`}
            note="thẻ còn nhớ tốt hôm nay"
            percent={Math.round(s.retention * 100)}
          />
        )}
      </div>
    </Sheet>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => ref.current?.focus(), []);
  return (
    <div ref={ref} role="alert" tabIndex={-1} className="mt-8 flex flex-col items-start gap-4 outline-none">
      <p className="m-0 text-read">
        Không tải được thống kê.
      </p>
      <Button type="button" onClick={onRetry}>
        Thử lại
      </Button>
    </div>
  );
}

export function StatsScreen({ state }: { state: StatsState }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const data = useMemo(() => statsFixture(state), [state]);
  const subjects = useMemo(
    () =>
      [...data.subjects].sort((a, b) => (a.examOn ?? "9999").localeCompare(b.examOn ?? "9999")),
    [data],
  );
  const wanted = params.get("subject") ?? ALL;
  const chosen = subjects.find((s) => s.id === wanted);
  const scope = useMemo(() => (chosen ? [chosen] : subjects), [chosen, subjects]);
  const cells = useMemo(
    () => buildGrid(scope, data.events, data.today, chosen?.id),
    [scope, data, chosen],
  );
  const examBy: Record<string, string[]> = {};
  for (const s of scope) if (s.examOn) (examBy[s.examOn] ??= []).push(s.name);

  function setSubject(id: string) {
    const next = new URLSearchParams(params.toString());
    if (id === ALL) next.delete("subject");
    else next.set("subject", id);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }

  if (state === "loading") {
    return (
      <>
        <h1 className="m-0 text-title">Thống kê</h1>
        <Skeleton />
      </>
    );
  }
  if (state === "error") {
    return (
      <>
        <h1 className="m-0 text-title">Thống kê</h1>
        <ErrorState onRetry={() => router.replace(pathname)} />
      </>
    );
  }
  if (data.events.length === 0 && scope.length === 0) {
    return (
      <>
        <h1 className="m-0 text-title">Thống kê</h1>
        <div className="mt-8 flex flex-col items-start gap-4">
          <p className="m-0 max-w-xl text-read">
            Thống kê hiện sau tuần học đầu tiên. Nộp bài ở một buổi học để bắt đầu.
          </p>
          <Button render={<a href="/today" />} nativeButton={false}>
            Vào buổi học
          </Button>
        </div>
      </>
    );
  }

  const scopeHasDays = cells.some((c) => c.cardsSaved + c.questionsAnswered > 0);
  return (
    <>
      <div className="flex flex-col gap-4 min-[768px]:flex-row min-[768px]:items-end min-[768px]:justify-between">
        <div>
          <h1 className="m-0 text-title">Thống kê</h1>
          <a href="#activity" className="mt-1 inline-flex min-h-11 items-center text-meta underline">
            Hoạt động theo ngày
          </a>
        </div>
        <div className="flex flex-col gap-3 min-[768px]:flex-row min-[768px]:items-end">
          <div className="flex min-w-0 flex-col gap-1 min-[768px]:w-72">
            <label htmlFor="stats-subject" className="text-meta text-ink-soft">
              Môn
            </label>
            <Select id="stats-subject" value={chosen?.id ?? ALL} onChange={(e) => setSubject(e.target.value)}>
              <option value={ALL}>Tất cả môn</option>
              {subjects.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          </div>
          <Button
            render={<a href="#" />}
            nativeButton={false}
            variant="secondary"
            className="max-sm:w-full"
          >
            Tải dữ liệu (CSV)
          </Button>
        </div>
      </div>

      <div className="mt-8 grid gap-(--bento-gap) [grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr))]">
        {scope.map((s) => (
          <SubjectBlock key={s.id} s={s} open={scope.length === 1} />
        ))}
      </div>

      <Sheet id="activity" className="mt-(--bento-gap) min-w-0" aria-labelledby="activity-h" role="region">
        <h2 id="activity-h" className="m-0 mb-4 text-read font-semibold">
          Hoạt động theo ngày
        </h2>
        {scopeHasDays ? null : (
          <div className="mb-4 flex flex-col items-start gap-3">
            <p className="m-0">
              Chưa có ngày nào học. Ô sẽ đậm lên khi bạn lưu thẻ hoặc làm câu hỏi.
            </p>
            <Button render={<a href="/today" />} nativeButton={false}>
              Vào buổi học
            </Button>
          </div>
        )}
        <ActivityGrid
          key={chosen?.id ?? ALL}
          cells={cells}
          today={data.today}
          subjects={subjects.map((s) => ({ id: s.id, name: s.name }))}
          examBy={examBy}
        />
      </Sheet>
    </>
  );
}
