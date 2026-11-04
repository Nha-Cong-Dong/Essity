import { Marker } from "@/components/notebook";
import { Sticker } from "@/components/motifs";
import { StartButton } from "@/components/today/start-button";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { formatExamDate } from "@/lib/exam-date";
import type { Today } from "@/lib/today";
import { dayLabel, extraSessions, TODAY_COPY } from "@/lib/today-copy";

// T2.14 (US-03, DESIGN.md §6.3, screens-html today.html): the day's session as a bento. Exactly
// one primary button per state. T4.13a: "Ghi buổi học" goes to /subjects/{id}/sessions/new.

const newSession = (subjectId: string) => `/subjects/${subjectId}/sessions/new`;

function Heading({ day }: { day: string }) {
  return (
    <div className="mb-8 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
      <h1 className="m-0 font-display text-title">
        <Marker>Hôm nay</Marker>
      </h1>
      <p className="m-0 text-read text-ink-soft">{dayLabel(day)}</p>
    </div>
  );
}

function SubjectsTile({ subjects }: { subjects: Today["subjects"] }) {
  return (
    <Sheet variant="tile" className="min-w-0 min-[901px]:col-span-4" aria-labelledby="today-subjects">
      <h2 id="today-subjects" className="m-0 font-display text-lead">
        {TODAY_COPY.subjectsTile}
      </h2>
      <ul className="m-0 mt-4 flex list-none flex-col gap-3 p-0">
        {subjects.map((subject) => (
          <li key={subject.id} className="flex flex-wrap items-baseline justify-between gap-x-3">
            <span className="font-semibold wrap-anywhere">{subject.name}</span>
            <span className="whitespace-nowrap text-meta">thi {formatExamDate(subject.exam_date)}</span>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}

/** "Sau buổi học" (today.html): one Ghi buổi học per subject, named only when there are several. */
function AfterSessionTile({ subjects }: { subjects: Today["subjects"] }) {
  const several = subjects.length > 1;
  return (
    <Sheet
      variant="tile"
      tone="rose"
      className="min-w-0 min-[901px]:col-span-4"
      aria-labelledby="today-after"
    >
      <h2 id="today-after" className="m-0 font-display text-lead">
        {TODAY_COPY.afterSession}
      </h2>
      <p className="m-0 mt-2.5 text-ink-soft">{TODAY_COPY.whatDidYouLearn}</p>
      <div className="mt-4 flex flex-col items-start gap-2">
        {subjects.map((subject) => (
          <Button
            key={subject.id}
            render={<a href={newSession(subject.id)} />}
            nativeButton={false}
            variant={several ? "quiet" : "secondary"}
            className="wrap-anywhere whitespace-normal"
          >
            {several ? `${TODAY_COPY.logSession} · ${subject.name}` : TODAY_COPY.logSession}
          </Button>
        ))}
      </div>
    </Sheet>
  );
}

function HongTile({ children }: { children: React.ReactNode }) {
  return (
    <Sheet
      variant="tile"
      tone="hong"
      className="relative flex min-h-80 min-w-0 flex-col gap-3 min-[901px]:col-span-8 min-[901px]:row-span-2"
    >
      <Sticker icon="moon" className="top-7 right-8" />
      {children}
    </Sheet>
  );
}

function QuietTile({ children }: { children: React.ReactNode }) {
  return (
    <Sheet
      variant="tile"
      tone="rose"
      className="flex min-h-60 min-w-0 flex-col justify-end gap-3 min-[901px]:col-span-8 min-[901px]:row-span-2"
    >
      {children}
    </Sheet>
  );
}

function Session({ today }: { today: Today }) {
  if (today.state === "in_progress" && today.in_progress) {
    const { session_id, position, total } = today.in_progress;
    return (
      <HongTile>
        <p className="m-0 text-read">
          Đang ở: câu {position}/{total}
        </p>
        <div className="mt-auto">
          <Button
            render={<a href={`/review/${session_id}`} />}
            nativeButton={false}
            variant="primary-inverse"
            size="lg"
          >
            {TODAY_COPY.resume}
          </Button>
        </div>
      </HongTile>
    );
  }
  if (today.state === "ready" && today.session) {
    const { question_count, minutes, subjects } = today.session;
    return (
      <HongTile>
        <p className="m-0 text-read">{TODAY_COPY.lead}</p>
        <p className="m-0 mt-auto flex items-baseline gap-3">
          <span className="font-display text-mega">{question_count}</span>
          <span className="text-lead">{TODAY_COPY.questions}</span>
        </p>
        {/* A subject name may be one long word (CSDL_nâng_cao_…): it wraps, never widens the page. */}
        <p className="m-0 text-read wrap-anywhere">
          khoảng {minutes} phút · {subjects.map((subject) => subject.name).join(", ")}
        </p>
        <div className="mt-4">
          <StartButton variant="primary-inverse">{TODAY_COPY.start}</StartButton>
        </div>
      </HongTile>
    );
  }
  if (today.state === "rested") {
    return (
      <QuietTile>
        <h2 className="m-0 font-display text-title">{TODAY_COPY.rested}</h2>
        {today.next_day && (
          <p className="m-0 text-read">
            {TODAY_COPY.nextSession} <b>{dayLabel(today.next_day)}</b>
          </p>
        )}
      </QuietTile>
    );
  }
  if (today.state === "no_questions") {
    return (
      <HongTile>
        <p className="m-0 text-read">{TODAY_COPY.lead}</p>
        <h2 className="m-0 mt-auto max-w-[18ch] font-display text-title">{TODAY_COPY.firstSession}</h2>
        <div className="mt-4">
          <Button
            render={<a href={newSession(today.subjects[0].id)} />}
            nativeButton={false}
            variant="primary-inverse"
            size="lg"
          >
            {TODAY_COPY.logSession}
          </Button>
        </div>
      </HongTile>
    );
  }
  return (
    <QuietTile>
      <p data-copy="tam" className="m-0 text-read">
        Các môn của bạn đều đã thi xong.
      </p>
    </QuietTile>
  );
}

export function TodayScreen({ today }: { today: Today }) {
  if (today.state === "no_subjects") {
    return (
      <>
        <Heading day={today.learning_day} />
        <section className="flex flex-col items-start gap-3 py-8" aria-labelledby="today-empty">
          <p id="today-empty" className="m-0 font-display text-title">
            {TODAY_COPY.noSubjects}
          </p>
          <p className="m-0 text-read text-ink-soft">{TODAY_COPY.noSubjectsHint}</p>
          <Button render={<a href="/subjects/new" />} nativeButton={false} className="mt-3">
            {TODAY_COPY.createSubject}
          </Button>
        </section>
      </>
    );
  }
  return (
    <>
      <Heading day={today.learning_day} />
      <div className="grid gap-6 min-[901px]:grid-cols-12">
        <Session today={today} />
        <SubjectsTile subjects={today.subjects} />
        {today.state !== "all_exams_over" && today.state !== "no_questions" && (
          <AfterSessionTile subjects={today.subjects} />
        )}
        {today.backlog && (
          <Sheet
            variant="tile"
            className="flex min-w-0 flex-wrap items-center justify-between gap-5 min-[901px]:col-span-12"
            aria-label="Lịch ôn trước kỳ thi"
          >
            <p data-copy="tam" className="m-0 text-read wrap-anywhere">
              Để kịp thi {today.backlog.subject_name} cần thêm khoảng{" "}
              {extraSessions(today.backlog.sessions, today.backlog.days)} phiên trong{" "}
              {today.backlog.days} ngày.
            </p>
            <StartButton variant="secondary" data-copy="tam">
              Ôn thêm
            </StartButton>
          </Sheet>
        )}
      </div>
    </>
  );
}

/** While /v1/today loads: the bento's shape, never a page spinner (DESIGN.md §6.3). */
export function TodayLoading() {
  return (
    <div aria-busy="true" className="grid gap-6 min-[901px]:grid-cols-12">
      <div className="h-80 rounded-tile bg-sunken min-[901px]:col-span-8 min-[901px]:row-span-2" />
      <div className="h-40 rounded-tile bg-sunken min-[901px]:col-span-4" />
      <p className="sr-only" role="status">
        Đang tải phiên hôm nay.
      </p>
    </div>
  );
}

/** /v1/today failed (DESIGN.md §6.3): a notice and Thử lại, never a guess. */
export function TodayFailed() {
  return (
    <div role="alert" className="flex max-w-160 flex-col items-start gap-2 rounded-sheet bg-sunken p-6">
      <p className="m-0">
        <b>{TODAY_COPY.failed}</b> {TODAY_COPY.failedHint}
      </p>
      <Button render={<a href="/today" />} nativeButton={false} variant="secondary" className="mt-3">
        {TODAY_COPY.retry}
      </Button>
    </div>
  );
}
