import type { AuthResult } from "@/lib/auth-errors";

export type ResetState =
  | { view: "loading" }
  | { view: "form"; token: string; error?: string; retryAfter?: number }
  | { view: "done" }
  | { view: "expired" };

/**
 * The screen after "Lưu mật khẩu" (F6). Only an expired or used link leaves the form: the URL
 * no longer has the token, so anything else (a refused password, a 429, a network failure)
 * must keep it, or one short password would cost the user their link.
 */
export function afterReset(token: string, result: AuthResult<unknown>): ResetState {
  if (result.data) return { view: "done" };
  if (result.error === "invalid_or_expired_token") return { view: "expired" };
  return { view: "form", token, error: result.error, retryAfter: result.retryAfter };
}
