"use client";

import { Markdown } from "@/components/markdown/markdown";
import { useEffect, useState } from "react";

import { loadUnitsBySection, type SectionGroup } from "@/lib/session-study/by-section";

// T7.12d (US-02b AC14): the subject's cards by outline section, below the session. Cards in no
// section come last under their own heading. Nothing is shown while there are no cards.

export function UnitsBySection({ subjectId, fetchFn }: { subjectId: string; fetchFn?: typeof fetch }) {
  const [groups, setGroups] = useState<SectionGroup[] | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    void loadUnitsBySection(subjectId, fetchFn).then((found) => {
      if (live) setGroups(found);
    });
    return () => {
      live = false;
    };
  }, [subjectId, fetchFn]);

  if (groups === undefined) return null;
  if (groups === null) return <p className="m-0 text-meta text-ink-soft">Chưa tải được danh sách thẻ theo phần.</p>;
  if (groups.length === 0) return null;
  return (
    <section aria-labelledby="by-section-h" className="flex flex-col gap-4 border-t border-line pt-6">
      <h2 id="by-section-h" className="m-0 font-display text-lead">
        Thẻ theo phần
      </h2>
      {groups.map((group) => (
        <div key={group.section_id ?? "none"} className="flex flex-col gap-2">
          <h3 className="m-0 break-words text-body font-medium">
            {group.section_title ?? "Chưa gắn phần"} <span className="text-ink-soft">({group.units.length})</span>
          </h3>
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {group.units.map((card) => (
              <li key={card.id} className="flex flex-col gap-1 break-words">
                <span className="text-body">
                  {card.title}
                  {card.status === "draft" && <span className="text-meta text-ink-soft"> · nháp</span>}
                </span>
                <Markdown className="text-meta text-ink-soft" text={card.content} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
