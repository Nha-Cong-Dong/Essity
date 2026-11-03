import type { SubjectEntry } from "@/lib/subject-entries";

// T7.13b (DESIGN §6.5 item 4): text and number entries into the subject's sub-screens, separated by
// rules. Plain links (no cards); they wrap onto the next line on a narrow screen.
export function SubjectEntryRow({ entries }: { entries: SubjectEntry[] }) {
  if (entries.length === 0) return null;
  return (
    <nav aria-label="Màn của môn" data-entry-row>
      <ul className="m-0 flex list-none flex-wrap p-0">
        {entries.map((entry) => (
          <li key={entry.key} className="border-l border-line first:border-l-0">
            <a
              href={entry.href}
              data-entry={entry.key}
              className="flex min-h-11 flex-col justify-center px-4 py-1 first:pl-0 wrap-anywhere"
            >
              <span className="font-semibold underline">{entry.label}</span>
              {entry.note !== null && <span className="text-small text-ink-soft">{entry.note}</span>}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
