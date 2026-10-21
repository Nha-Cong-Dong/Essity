// Every sentence the account screens show for an error code from web's /api/auth routes
// (DESIGN.md §6.1). One place, so a sentence is changed once (W8).

const MESSAGES: Record<string, string> = {
  // AC5: the same sentence whatever was wrong, so it reveals no account.
  invalid_credentials: "Email hoặc mật khẩu không đúng.",
  // AC6: no count of attempts left.
  rate_limited: "Bạn đã thử quá nhiều lần. Thử lại sau 15 phút.",
  unavailable: "Chưa gửi được. Kiểm tra kết nối rồi thử lại.",
};

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
    : { status: response.status, error: json.error ?? "unavailable", retryAfter };
}
