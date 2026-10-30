// T8.7a (US-16, DESIGN §6.12): the Luyện tập screen's data shape and the small pure pieces of its copy.
// No timer, no ranking: time is information (US-16 AC5).

export type PracticeQuestion = {
  id: string;
  /** The question's number in the bank, for "Câu 7". */
  number: number;
  summary: string;
  origin: "bank" | "generated";
  /** ready: can be done; waiting: its section is not studied yet; unlinked: no section attached. */
  status: "ready" | "waiting" | "unlinked";
  sectionLabel?: string;
  /** Where the answer came from: the bank, or written by the AI (labelled, US-14 AC / §6.9). */
  answerSource: "bank" | "ai";
  practiced: boolean;
  mastered: boolean;
};

export type Timing = { kind: "faster" | "near" | "slower" | "unknown" | "unmeasured"; refMinutes?: number };

export const MASTERY_MIN_ATTEMPTS = 3;

const formatScore = (score: number) => String(score).replace(".", ",");

/** "đúng 7 trên 10 lần gần nhất"; under 3 attempts there is nothing to say yet. */
export function masteryText({ score, attempts }: { score: number; attempts: number }): string {
  if (attempts < MASTERY_MIN_ATTEMPTS) return "chưa đủ dữ liệu";
  return `đúng ${formatScore(score)} trên ${attempts} lần gần nhất`;
}

const TIMING_WORDS: Record<Timing["kind"], string> = {
  faster: "thường nhanh hơn mốc tham khảo",
  near: "gần mốc tham khảo",
  slower: "chậm hơn mốc tham khảo",
  unknown: "chưa đủ dữ liệu",
  unmeasured: "chưa đo",
};

export function timingLine({ kind, refMinutes }: Timing): string {
  const words = TIMING_WORDS[kind];
  return refMinutes && kind !== "unmeasured" ? `${words} · khoảng ${refMinutes} phút mỗi câu` : words;
}

const RANK = { ready: 0, waiting: 1, unlinked: 2 } as const;

/** Ready first (never-attempted before practiced, keeping the given newest-first order), then waiting. */
export function orderedRows(rows: PracticeQuestion[], removed: ReadonlySet<string>): PracticeQuestion[] {
  return rows
    .map((row, index) => ({ row, index }))
    .filter(({ row }) => !removed.has(row.id))
    .sort((a, b) => RANK[a.row.status] - RANK[b.row.status] || Number(a.row.practiced) - Number(b.row.practiced) || a.index - b.index)
    .map(({ row }) => row);
}

export function summaryLine(rows: PracticeQuestion[], removed: ReadonlySet<string>): string {
  const live = rows.filter((row) => !removed.has(row.id));
  const ready = live.filter((row) => row.status === "ready").length;
  const practiced = live.filter((row) => row.practiced).length;
  const mastered = live.filter((row) => row.mastered).length;
  return `${ready} câu sẵn sàng · ${practiced} đã luyện · ${mastered} đã thuộc`;
}
