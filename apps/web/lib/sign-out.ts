import { type AuthResult, postJson } from "@/lib/auth-errors";
import { clearAllDrafts } from "@/lib/draft";
import { safeNext } from "@/lib/landing";

type Deps = {
  post?: (path: string) => Promise<AuthResult<{ next: string }>>;
  assign?: (url: string) => void;
  /** Where to go instead of web's answer (F2: /register after "Sai email?"). */
  then?: string;
  /** Drops the answers kept on this device (T2.15): the next person here must not see them. */
  clearDrafts?: () => void;
};

/**
 * Signs out through web and leaves only once web has cleared the cookie. On a refusal or a
 * network failure it stays, so nobody walks away from a shared computer still signed in.
 */
export async function signOut({
  post = postJson,
  assign = (url) => window.location.assign(url),
  then,
  clearDrafts = clearAllDrafts,
}: Deps = {}): Promise<boolean> {
  const result = await post("/api/auth/logout");
  if (!result.data) return false;
  clearDrafts();
  assign(then ?? safeNext(result.data.next, ["/login"], "/login"));
  return true;
}
