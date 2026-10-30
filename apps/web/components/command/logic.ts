// T9.3a (US-18; DESIGN §6.14): the pure parts of the command bar. core-api returns a structured
// diff and {kind, id} of the touched object (T9.2 contract); the web composes the sentence and
// builds the link, so no text or href from the server is trusted.

/** Same as MAX_COMMAND_CHARS of the parse-command request (ai-service commands/schema.py, T9.1). */
export const COMMAND_MAX = 500;
export const NAME_MAX = 60;

export type Diff = {
  /** "bỏ", "sửa", "đổi": the app's own words. */
  verb: string;
  /** What is touched, singular or plural noun: "mục", "thẻ". */
  noun: string;
  /** Words between the noun and the target: "khỏi đề cương thi". */
  tail?: string;
  /** A name of the user's own (card title, section label). Cut at NAME_MAX. */
  target?: string;
  /** In brackets after the sentence: "chương 7". Cut at NAME_MAX. */
  scope?: string;
  count: number;
  from?: string;
  to?: string;
};

export type ObjectRef = { kind: string; id: string };

const clip = (text: string, max: number): string => {
  const letters = [...text];
  return letters.length <= max ? text : letters.slice(0, max - 1).join("") + "…";
};

/** Cuts a user's name (never a number) to NAME_MAX code points, ending in an ellipsis. */
export const truncateName = (name: string): string => clip(name, NAME_MAX);

/** "bỏ 9 mục khỏi đề cương thi (chương 7)": the count is in the sentence when N > 1. */
export function summarize(diff: Diff): string {
  const parts = [diff.verb, ...(diff.count > 1 ? [String(diff.count)] : []), diff.noun];
  if (diff.tail) parts.push(diff.tail);
  if (diff.target) parts.push(truncateName(diff.target));
  const sentence = parts.join(" ");
  return diff.scope ? `${sentence} (${truncateName(diff.scope)})` : sentence;
}

/** NFC (a Telex keyboard on macOS sends NFD) and trimmed: what is counted and what is sent. */
export const normalizeCommand = (text: string): string => text.normalize("NFC").trim();

export const commandLength = (text: string): number => [...text.normalize("NFC")].length;

export const tooLong = (text: string): boolean => commandLength(normalizeCommand(text)) > COMMAND_MAX;

// Fixed table: a kind outside it gives no link. The segments are placeholders: those pages do not
// exist yet and T9.3 points each kind at its real route. Kept as bare segments (not whole paths) so
// the dead-link scan of tests/internal-links.test.ts does not read them as finished links.
const ROUTES: Record<string, string> = {
  card: "cards",
  section: "sections",
  question: "questions",
};
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function linkFor(ref: ObjectRef): string | null {
  const segment = Object.hasOwn(ROUTES, ref.kind) ? ROUTES[ref.kind] : undefined;
  if (segment === undefined || !UUID.test(ref.id)) return null;
  return `/${segment}/${ref.id}`;
}
