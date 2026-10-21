// Small helpers for web's own route handlers (app/api/**).

/** The JSON body's string fields `names`, or null when the body is not that shape. */
export async function readStrings<Name extends string>(
  request: Request,
  names: readonly Name[],
): Promise<Record<Name, string> | null> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return null;
  }
  if (typeof body !== "object" || body === null) return null;
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
