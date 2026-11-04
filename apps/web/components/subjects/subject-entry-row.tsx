import type { SubjectEntry } from "@/lib/subject-entries";

// T7.13b (DESIGN §6.5 item 4): text and number entries into the subject's sub-screens, separated by
// rules. Plain links (no cards); they wrap onto the next line on a narrow screen.
export function SubjectEntryRow({ entries }: { entries: SubjectEntry[] }) {
  if (entries.length === 0) return null;
  return (
    <nav aria-label="Màn của môn" data-entry-row>
      <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
        {entries.map((entry) => (
          <li key={entry.key}>
            <a
              href={entry.href}
              data-entry={entry.key}
              className="flex min-h-11 flex-col justify-center rounded-full bg-sheet px-5 py-1 break-words no-underline inset-ring-1 inset-ring-line-strong hover:bg-sunken"
            >
              <span className="font-semibold">{entry.label}</span>
              {entry.note !== null && <span className="text-small text-ink-soft">{entry.note}</span>}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
