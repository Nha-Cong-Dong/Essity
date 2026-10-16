import "server-only";

// core-api is never exposed to the internet (ARCH §3); only the web server talks to it.
const CORE_API_URL = process.env.CORE_API_URL ?? "http://127.0.0.1:8000";
const DEFAULT_TIMEOUT_MS = 3000;

export async function coreFetch(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(new URL(path, CORE_API_URL), {
    cache: "no-store",
    signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
    ...init,
  });
}
