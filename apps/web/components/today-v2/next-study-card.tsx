import { SubjectMark } from "@/components/subject-mark";
import { NxRow } from "@/components/ui/nx-list";
import { studyHref } from "@/lib/session-study/entry";
import { paceLine, TODAY_V2_COPY as COPY, type LearnItem } from "@/lib/today-v2";

// T7.13a (US-15 AC1, AC7; DESIGN §6.2 "Học gì tiếp"), V22: one subject as a row of the landing's
// "nx" tile: letter | name + the section | state. The one `next` row of the tile is the cam row.
// Words are never cut mid-word; a name that does not fit goes to the next line.

export function PaceLine({ pace }: { pace: Extract<LearnItem, { state: "next" }>["pace"] }) {
  return <span className="block text-meta font-normal text-ink-soft break-words">{paceLine(pace)}</span>;
}

export function NextStudyRow({ item, next = false }: { item: LearnItem; next?: boolean }) {
  const base = `/subjects/${item.subject.id}`;
  const name = <span className="block font-semibold break-words">{item.subject.name}</span>;
  const lead = <SubjectMark name={item.subject.name} />;
  if (item.state === "next") {
    return (
      <NxRow
        lead={lead}
        next={next}
        // The "next" label sits under the name, so a narrow column keeps the whole name line.
        why={
          next ? (
            <>
              <span aria-hidden="true">→ </span>
              {COPY.nextState}
            </>
          ) : undefined
        }
        href={studyHref(item.subject.id, item.section.id)}
      >
        {name}
        <span className="block font-normal break-words">
          {item.section.label ? `Phần ${item.section.label} ` : ""}
          {item.section.title}
          {item.section.pages ? ` · ${item.section.pages}` : ""}
        </span>
        <PaceLine pace={item.pace} />
      </NxRow>
    );
  }
  if (item.state === "no_textbook") {
    return (
      <NxRow lead={lead} state={COPY.uploadTextbook} href={`${base}/documents`}>
        {name}
        <span className="block text-meta font-normal text-ink-soft break-words">
          Môn {item.subject.name} {COPY.noTextbook}
        </span>
      </NxRow>
    );
  }
  return (
    <NxRow lead={lead}>
      {name}
      <span className="block text-meta font-normal text-ink-soft">{COPY.finished}</span>
    </NxRow>
  );
}
