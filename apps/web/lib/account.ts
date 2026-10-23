import "server-only";

import type { NextRequest } from "next/server";

import { PENDING_EMAIL_COOKIE, SESSION_COOKIE } from "@/lib/cookies";
import { type components, coreClientFor } from "@/lib/core-client";
import { errorName, logError, type LogRoute } from "@/lib/log";

// For route handlers, which read cookies from the request (lib/session.ts is for pages).

type Me = components["schemas"]["Me"];

/** The signed-in user, asked of core-api; null without a cookie or when it is not a session. */
export async function sessionUser(request: NextRequest): Promise<Me | null> {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return null;
  const { data } = await coreClientFor(request, token).GET("/v1/me");
  return data ?? null;
}

/**
 * `sessionUser` for a step that goes on without it when core-api fails: the failure is logged
 * (a status other than 200 or 401, or the type of what was thrown), never thrown (R12).
 */
export async function sessionUserOrNull(request: NextRequest, route: LogRoute): Promise<Me | null> {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return null;
  try {
    const { data, response } = await coreClientFor(request, token).GET("/v1/me");
    if (response.status !== 200 && response.status !== 401) {
      logError("core-api call failed", { route, status: response.status });
    }
    return data ?? null;
  } catch (error) {
    logError("core-api call failed", { route, error: errorName(error) });
    return null;
  }
}

/** The email just signed up with (F1), or null. Next has already decoded the cookie. */
export function pendingEmail(request: NextRequest): string | null {
  return request.cookies.get(PENDING_EMAIL_COOKIE)?.value || null;
}
