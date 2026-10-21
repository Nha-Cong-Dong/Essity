// Small helpers for web's own route handlers (app/api/**).

// Account forms send a few short fields; anything bigger is refused before it fills memory.
const MAX_BODY_BYTES = 8 * 1024;

/** The body as text, or null once it passes MAX_BODY_BYTES (read as a stream, never whole). */
async function readLimited(request: Request): Promise<string | null> {
  if (Number(request.headers.get("content-length")) > MAX_BODY_BYTES) return null;
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BODY_BYTES) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  return new TextDecoder().decode(Buffer.concat(chunks));
}

/** The JSON body's string fields `names`, or null when the body is not that shape. */
export async function readStrings<Name extends string>(
  request: Request,
  names: readonly Name[],
): Promise<Record<Name, string> | null> {
  const text = await readLimited(request);
  if (text === null) return null;
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    return null;
  }
  if (typeof body !== "object" || body === null || Array.isArray(body)) return null;
  const fields = body as Record<string, unknown>;
  if (!names.every((name) => typeof fields[name] === "string")) return null;
  return Object.fromEntries(names.map((name) => [name, fields[name]])) as Record<Name, string>;
}

/** An error the browser can show (lib/auth-errors.ts has its sentence). */
export function errorResponse(error: string, status: number, headers?: HeadersInit): Response {
  return Response.json({ error }, { status, headers });
}

/**
 * core-api could not answer. Logged with a fixed message and the error's type only: the
 * request carried a password or a token (ADR-0013).
 */
export function unavailable(route: string, error?: unknown): Response {
  console.error("core-api call failed", {
    route,
    error: error instanceof Error ? error.name : undefined,
  });
  return errorResponse("unavailable", 503);
}

/** Passes core-api's 429 on, with its Retry-After and nothing else (AC6). */
export function rateLimited(response: Response): Response {
  const retryAfter = response.headers.get("retry-after");
  return errorResponse("rate_limited", 429, retryAfter ? { "retry-after": retryAfter } : undefined);
}
