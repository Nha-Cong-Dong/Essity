import { errorName, type LogRoute, logError } from "@/lib/log";

// Small helpers for web's own route handlers (app/api/**).

// Account forms send a few short fields; anything bigger is refused before it fills memory.
const MAX_BODY_BYTES = 8 * 1024;

/** The body as text, or null once it passes `maxBytes` (read as a stream, never whole). */
async function readLimited(request: Request, maxBytes: number): Promise<string | null> {
  if (Number(request.headers.get("content-length")) > maxBytes) return null;
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > maxBytes) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  return new TextDecoder().decode(Buffer.concat(chunks));
}

/** The JSON body as an object, or null when it is too big, not JSON or not an object. */
async function readObject(
  request: Request,
  maxBytes = MAX_BODY_BYTES,
): Promise<Record<string, unknown> | null> {
  const text = await readLimited(request, maxBytes);
  if (text === null) return null;
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    return null;
  }
  if (typeof body !== "object" || body === null || Array.isArray(body)) return null;
  return body as Record<string, unknown>;
}

/** The JSON body's string fields `names`, or null when the body is not that shape. */
export async function readStrings<Name extends string>(
  request: Request,
  names: readonly Name[],
): Promise<Record<Name, string> | null> {
  const fields = await readObject(request);
  if (fields === null) return null;
  if (!names.every((name) => typeof fields[name] === "string")) return null;
  return Object.fromEntries(names.map((name) => [name, fields[name]])) as Record<Name, string>;
}

type FieldKind = { string: string; integer: number; boolean: boolean };
type FieldSpec = { kind: keyof FieldKind; optional?: boolean };
type Fields<Spec extends Record<string, FieldSpec>> = {
  [Name in keyof Spec as Spec[Name]["optional"] extends true ? never : Name]: FieldKind[Spec[Name]["kind"]];
} & {
  [Name in keyof Spec as Spec[Name]["optional"] extends true ? Name : never]?: FieldKind[Spec[Name]["kind"]];
};

const IS_KIND: Record<keyof FieldKind, (value: unknown) => boolean> = {
  string: (value) => typeof value === "string",
  integer: (value) => Number.isSafeInteger(value),
  boolean: (value) => typeof value === "boolean",
};

/**
 * The JSON body read by `spec`: each field of its type, optional ones left out when missing, and
 * no other key. Null otherwise. What a route sends on is built from this, never the browser's JSON
 * (review plan R1). `maxBytes` raises the 8 KB limit for a body that carries an answer.
 */
export async function readFields<Spec extends Record<string, FieldSpec>>(
  request: Request,
  spec: Spec,
  { maxBytes }: { maxBytes?: number } = {},
): Promise<Fields<Spec> | null> {
  const body = await readObject(request, maxBytes);
  if (body === null) return null;
  if (!Object.keys(body).every((name) => Object.hasOwn(spec, name))) return null;
  const fields: Record<string, unknown> = {};
  for (const [name, { kind, optional }] of Object.entries(spec)) {
    if (!Object.hasOwn(body, name)) {
      if (optional) continue;
      return null;
    }
    if (!IS_KIND[kind](body[name])) return null;
    fields[name] = body[name];
  }
  return fields as Fields<Spec>;
}

/** An error the browser can show (lib/auth-errors.ts has its sentence). */
export function errorResponse(error: string, status: number, headers?: HeadersInit): Response {
  return Response.json({ error }, { status, headers });
}

/**
 * core-api could not answer. Logged with a fixed message and the error's type only: the
 * request carried a password or a token (ADR-0013).
 */
export function unavailable(route: LogRoute, error?: unknown): Response {
  logError("core-api call failed", { route, error: errorName(error) });
  return errorResponse("unavailable", 503);
}

/** Passes core-api's 429 on, with its Retry-After and nothing else (AC6). */
export function rateLimited(response: Response): Response {
  const retryAfter = response.headers.get("retry-after");
  return errorResponse("rate_limited", 429, retryAfter ? { "retry-after": retryAfter } : undefined);
}
