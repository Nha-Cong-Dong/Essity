import "server-only";

import { context, propagation } from "@opentelemetry/api";

// core-api is never exposed to the internet (ARCH §3); only the web server talks to it.
export const CORE_API_URL = process.env.CORE_API_URL ?? "http://127.0.0.1:8000";
const DEFAULT_TIMEOUT_MS = 3000;

/**
 * The one way to call core-api. `path` must be a path on core-api ("/v1/me"): an absolute URL
 * would carry the session and service tokens to another host. Responses are never cached
 * (they belong to one user, W3), whatever the caller passes.
 */
export async function coreFetch(path: string, init: RequestInit = {}): Promise<Response> {
  if (!path.startsWith("/") || path.startsWith("//")) {
    throw new Error("coreFetch takes a path on core-api");
  }
  const headers = new Headers(init.headers);
  // W3C traceparent, so core-api continues the trace of the request being rendered.
  propagation.inject(context.active(), headers, {
    set: (carrier, key, value) => carrier.set(key, value),
  });
  return fetch(new URL(path, CORE_API_URL), {
    signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
    ...init,
    headers,
    cache: "no-store",
    next: undefined,
  });
}
