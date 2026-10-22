import { NextRequest } from "next/server";
import { vi } from "vitest";

export const ORIGIN = "http://localhost:3000";
export const SERVICE_TOKEN = "web-token-for-tests-only-0123456789";

/** A browser POST (or `method`) to one of web's own routes, from our own origin unless told otherwise. */
export function browserPost(
  path: string,
  body?: unknown,
  {
    origin = ORIGIN,
    cookies = {},
    method = "POST",
  }: { origin?: string | null; cookies?: Record<string, string>; method?: string } = {},
): NextRequest {
  const headers = new Headers({ "content-type": "application/json" });
  if (origin !== null) headers.set("origin", origin);
  const cookie = Object.entries(cookies)
    .map(([name, value]) => `${name}=${value}`)
    .join("; ");
  if (cookie) headers.set("cookie", cookie);
  return new NextRequest(`${ORIGIN}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

type CoreCall = { path: string; method: string; headers: Headers; body: unknown };

/**
 * Stand-in for core-api: `reply` answers each call; every call is recorded. The global fetch is
 * what coreFetch uses, so this sees exactly what web sends.
 */
export function fakeCoreApi(reply: (call: CoreCall) => Response | Promise<Response>) {
  const calls: CoreCall[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: URL, init: RequestInit = {}) => {
      const raw = init.body ? new TextDecoder().decode(init.body as ArrayBuffer) : "";
      const call = {
        path: url.pathname,
        method: init.method ?? "GET",
        headers: new Headers(init.headers),
        body: raw ? JSON.parse(raw) : undefined,
      };
      calls.push(call);
      return reply(call);
    }),
  );
  return calls;
}

/** The `Set-Cookie` lines of a response, by cookie name. */
export function setCookies(response: Response): Map<string, string> {
  return new Map(
    response.headers.getSetCookie().map((line) => [line.slice(0, line.indexOf("=")), line]),
  );
}
