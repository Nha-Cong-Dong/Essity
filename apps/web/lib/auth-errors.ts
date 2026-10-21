// Every sentence the account screens show for an error code from web's /api/auth routes
// (DESIGN.md §6.1). One place, so a sentence is changed once (W8).

const MESSAGES: Record<string, string> = {
  // AC5: the same sentence whatever was wrong, so it reveals no account.
  invalid_credentials: "Email hoặc mật khẩu không đúng.",
  // AC6: no count of attempts left.
  rate_limited: "Bạn đã thử quá nhiều lần. Thử lại sau 15 phút.",
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

/** The 60 seconds core-api waits between two emails to one address (AC2). */
export const RESEND_COOLDOWN_SECONDS = 60;

const FALLBACK = MESSAGES.unavailable;

export function authMessage(code: string | undefined): string {
  return (code !== undefined && MESSAGES[code]) || FALLBACK;
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
  const json = (await response.json().catch(() => ({}))) as Data & { error?: string };
  const retryAfter = Number(response.headers.get("retry-after")) || undefined;
  return response.ok
    ? { status: response.status, data: json }
    : { status: response.status, error: json.error ?? "unavailable", retryAfter, body: json };
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
