import { trace } from "@opentelemetry/api";

// Risk register R12, ADR-0013: web's one way to log. A JSON line like the Python services',
// joined to the request's trace, with only the fields below: never a message from an error
// (it may quote a URL or a body), an email, a token or anything the user typed.

/** Which call failed: a fixed name, never built from request data (review 501af99). */
export type LogRoute =
  | "baseline"
  | "baseline-next"
  | "baseline-skip"
  | "login"
  | "logout"
  | "password-reset"
  | "password-reset-confirm"
  | "register"
  | "resend"
  | "session-check"
  | "subject"
  | "subjects"
  | "verify-email";

type Fields = {
  route?: LogRoute;
  /** core-api's HTTP status, when it answered. */
  status?: number;
  /** The error's type ("TypeError"), never its message. */
  error?: string;
};

const ALLOWED = ["route", "status", "error"] as const;

export function logError(message: string, fields: Fields = {}): void {
  const line: Record<string, unknown> = {
    timestamp: new Date().toISOString(),
    level: "ERROR",
    service: "web",
    message,
  };
  for (const name of ALLOWED) {
    if (fields[name] !== undefined) line[name] = fields[name];
  }
  const span = trace.getActiveSpan()?.spanContext();
  if (span && trace.isSpanContextValid(span)) {
    line.trace_id = span.traceId;
    line.span_id = span.spanId;
  }
  console.error(JSON.stringify(line));
}

/** The type of what was thrown, the only part of an error that may be logged. */
export const errorName = (error: unknown): string | undefined =>
  error instanceof Error ? error.name : undefined;
