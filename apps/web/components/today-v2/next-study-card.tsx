import { Button } from "@/components/ui/button";
import { paceLine, TODAY_V2_COPY as COPY, type LearnItem } from "@/lib/today-v2";

// T7.13a (US-15 AC1, AC7; DESIGN §6.2 "Học gì tiếp"): one subject's block. The cover, name and
// the lines wrap anywhere (a name may be one long word); the same grid as the subjects list.

export function PaceLine({ pace }: { pace: Extract<LearnItem, { state: "next" }>["pace"] }) {
  return (
    <p className="m-0 text-meta text-ink-soft wrap-anywhere">
      {paceLine(pace)}
    </p>
  );
}

export function NextStudyCard({ item, primary }: { item: LearnItem; primary: boolean }) {
  const nameId = `learn-${item.subject.id}`;
  const base = `/subjects/${item.subject.id}`;
  const label = (text: string) => `${text} · ${item.subject.name}`;
  return (
    <article aria-labelledby={nameId} className="flex flex-col gap-2">
      <div className="grid grid-cols-[auto_minmax(0,1fr)] items-start gap-x-4">
        <span aria-hidden="true" className="h-10 w-8 rounded-slip bg-(color:--rose-200) shadow-sheet" />
        <h3 id={nameId} className="m-0 min-w-0 text-section font-semibold wrap-anywhere">
          {item.subject.name}
        </h3>
      </div>
      {item.state === "next" && (
        <>
          <p className="m-0 text-lead wrap-anywhere">
            Mục {item.section.label} {item.section.title}
            {item.section.pages ? ` · ${item.section.pages}` : ""}
          </p>
          <p className="m-0 text-body wrap-anywhere">
            {item.reason}
          </p>
          <PaceLine pace={item.pace} />
          <div className="mt-2">
            <Button
              render={<a href={`${base}/sessions/new`} />}
              nativeButton={false}
              variant={primary ? "primary" : "secondary"}
              aria-label={label(COPY.enter)}
              className="max-sm:w-full"
            >
              {COPY.enter}
            </Button>
          </div>
        </>
      )}
      {item.state === "no_textbook" && (
        <>
          <p className="m-0 text-body wrap-anywhere">
            Môn {item.subject.name} {COPY.noTextbook}
          </p>
          <div className="-ml-3">
            <Button
              render={<a href={`${base}/documents`} />}
              nativeButton={false}
              variant="quiet"
              aria-label={label(COPY.uploadTextbook)}
            >
              {COPY.uploadTextbook}
            </Button>
          </div>
        </>
      )}
      {item.state === "finished" && (
        <p className="m-0 text-body">
          {COPY.finished}
        </p>
      )}
    </article>
  );
}
