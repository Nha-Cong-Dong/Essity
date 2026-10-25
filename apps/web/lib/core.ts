import "server-only";

import { context, propagation } from "@opentelemetry/api";

import { webConfig } from "@/lib/config";

const DEFAULT_TIMEOUT_MS = 3000;

/**
 * The one way to call core-api. `path` must be a path on core-api ("/v1/me"): an absolute URL
 * would carry the session and service tokens to another host. Responses are never cached
 * (they belong to one user, W3), whatever the caller passes. `timeoutMs` is longer only where
 * core-api waits on the AI (submitting an answer, plan D-5).
 */
export async function coreFetch(
  path: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  if (!path.startsWith("/") || path.startsWith("//")) {
    throw new Error("coreFetch takes a path on core-api");
  }
  const headers = new Headers(init.headers);
  // W3C traceparent, so core-api continues the trace of the request being rendered.
  propagation.inject(context.active(), headers, {
    set: (carrier, key, value) => carrier.set(key, value),
  });
  return fetch(new URL(path, webConfig().coreApiUrl), {
    signal: AbortSignal.timeout(timeoutMs),
    ...init,
    headers,
    cache: "no-store",
    next: undefined,
  });
}
