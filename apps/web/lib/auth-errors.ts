// Every sentence the account screens show for an error code from web's /api/auth routes
// (DESIGN.md §6.1). One place, so a sentence is changed once (W8).

const MESSAGES: Record<string, string> = {
  // AC5: the same sentence whatever was wrong, so it reveals no account.
  invalid_credentials: "Email hoặc mật khẩu không đúng.",
  unavailable: "Chưa gửi được. Kiểm tra kết nối rồi thử lại.",
  // AC1: why a password was refused (core-api's domain/auth/passwords.py).
  too_short: "Mật khẩu cần ít nhất 8 ký tự. Không cần ký tự đặc biệt.",
  too_long: "Mật khẩu dài tối đa 128 ký tự.",
  common: "Mật khẩu này quá phổ biến, dễ bị đoán. Chọn mật khẩu khác.",
  same_as_email: "Mật khẩu không được giống email.",
  invalid_password: "Mật khẩu này không dùng được. Chọn mật khẩu khác.",
  invalid_email: "Email chưa đúng. Kiểm tra lại.",
};

/** Reasons core-api gives for refusing a password (422), passed on to the form. */
export const PASSWORD_REASONS = new Set(["too_short", "too_long", "common", "same_as_email"]);

/**
 * True when every field error in a 422 list is on the password. The only rule core-api checks
 * there is its 1024-character cap, so that reads as too_long (reviews bb28275 #1, 822b3ea #1).
 */
export function onlyPasswordTooLong(detail: unknown[]): boolean {
  return detail.every((error) => {
    const loc: unknown = (error as { loc?: unknown } | null)?.loc;
    return Array.isArray(loc) && loc.includes("password");
  });
}

/** core-api's 422 detail as a code the form shows: a password reason, or the given fallback. */
export function passwordReason(detail: unknown, fallback = "invalid_password"): string {
  return typeof detail === "string" && PASSWORD_REASONS.has(detail) ? detail : fallback;
}

/** The 60 seconds core-api waits between two emails to one address (AC2). */
export const RESEND_COOLDOWN_SECONDS = 60;

const FALLBACK = MESSAGES.unavailable;

export function authMessage(code: string | undefined): string {
  return (code !== undefined && MESSAGES[code]) || FALLBACK;
}

/**
 * The 429 box (AC6): DESIGN.md §6.1's sentence, with the minutes core-api's Retry-After gives.
 * Signing in locks for 15 minutes; signing up or resetting from one network can wait an hour.
 */
export function rateLimitMessage(retryAfterSeconds: number | undefined): string {
  const minutes = Math.max(1, Math.ceil((retryAfterSeconds ?? 15 * 60) / 60));
  return `Bạn đã thử quá nhiều lần. Thử lại sau ${minutes} phút.`;
}

export type AuthResult<Data> = {
  status: number;
  data?: Data;
  error?: string;
  /** Seconds, from Retry-After on a 429. */
  retryAfter?: number;
  /** The whole error body, for a route that says more than its code. */
  body?: Record<string, unknown>;
};

/** POST JSON to one of web's own routes, from the browser. A network failure is status 0. */
export async function postJson<Data>(path: string, body?: unknown): Promise<AuthResult<Data>> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    return { status: 0, error: "unavailable" };
  }
  // Web's routes always answer a JSON object (review plan P7). Anything else, even with a 2xx,
  // means something in between broke: unavailable, never an empty success (R22).
  const parsed: unknown = await response.json().catch(() => undefined);
  const json = (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed) ? parsed : undefined) as
    | (Data & { error?: string })
    | undefined;
  const retryAfter = Number(response.headers.get("retry-after")) || undefined;
  if (response.ok) {
    return json ? { status: response.status, data: json } : { status: response.status, error: "unavailable" };
  }
  return { status: response.status, error: json?.error ?? "unavailable", retryAfter, body: json };
}

/**
 * Seconds before "Gửi lại" works again (F3). The countdown is only a hint: core-api decides,
 * and its 429 restarts the countdown rather than showing an error.
 */
export function resendWait(result: AuthResult<unknown>): number {
  if (result.data) return RESEND_COOLDOWN_SECONDS;
  if (result.status === 429) return result.retryAfter ?? RESEND_COOLDOWN_SECONDS;
  return 0;
}
