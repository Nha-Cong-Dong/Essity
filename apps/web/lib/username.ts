// Usernames (US-12 D2), checked in the browser only to say which rule was missed; core-api
// (domain/auth/username.py) decides. Typed text is lowercased as it goes.

export const USERNAME_MIN = 3;
export const USERNAME_MAX = 20;

/** The text of a username field as the server will read it: lowercased. */
export function normalizeUsername(value: string): string {
  return value.toLowerCase();
}

/** The rule a username breaks, as a sentence, or null when its shape is fine. One rule at a time. */
export function usernameProblem(username: string): string | null {
  if (!/^[a-z0-9_.]+$/.test(username)) return "Chỉ dùng chữ không dấu, số, _ và .";
  if (!/^[a-z]/.test(username)) return "Bắt đầu bằng một chữ cái.";
  if (username.includes("..")) return "Không dùng hai dấu chấm liền nhau.";
  if (username.length < USERNAME_MIN || username.length > USERNAME_MAX) {
    return `Tên đăng nhập cần ${USERNAME_MIN}–${USERNAME_MAX} ký tự.`;
  }
  return null;
}

/** An email's shape, only enough to catch "an@gmail": the server has the last word. */
export function emailProblem(email: string): string | null {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) ? null : "Email chưa đúng dạng, ví dụ an@gmail.com";
}
