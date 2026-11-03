import "server-only";

import type { NextRequest } from "next/server";

import { clientIpFrom } from "@/lib/client-ip";
import { webConfig } from "@/lib/config";
import { coreFetch } from "@/lib/core";
import { errorResponse, unavailable } from "@/lib/http";
import { SESSION_COOKIE } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";

// Browser -> web -> core-api for one vault card. The body is rebuilt from two checked strings.

export async function forwardCard(
  request: NextRequest,
  id: string,
  method: "GET" | "PATCH" | "DELETE",
  suffix = "",
  body?: { title?: string; content?: string },
): Promise<Response> {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!token) return errorResponse("signed_out", 401);
  if (!isSubjectId(id)) return errorResponse("card_not_found", 404);
  const headers = new Headers({ accept: "application/json", authorization: `Bearer ${token}` });
  const { serviceToken, trustedProxyHops } = webConfig();
  if (serviceToken) {
    headers.set("X-Service-Token", serviceToken);
    const ip = clientIpFrom(request.headers, trustedProxyHops);
    if (ip) headers.set("X-Client-IP", ip);
  }
  if (body) headers.set("content-type", "application/json");
  try {
    const response = await coreFetch(`/v1/vault/cards/${id}${suffix}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (response.status === 204) return new Response(null, { status: 204 });
    if (response.status === 401) return errorResponse("signed_out", 401);
    if (response.ok) return Response.json(await response.json(), { status: 200 });
    if (response.status === 404) return errorResponse("card_not_found", 404);
    if (response.status === 422) return errorResponse("invalid_request", 422);
    return errorResponse("unavailable", 503);
  } catch (error) {
    return unavailable("documents", error);
  }
}

export function readCardEdit(value: unknown): { title?: string; content?: string } | null {
  if (typeof value !== "object" || value === null) return null;
  const { title, content } = value as Record<string, unknown>;
  const out: { title?: string; content?: string } = {};
  if (title !== undefined) {
    if (typeof title !== "string" || title.trim() === "" || title.length > 200) return null;
    out.title = title;
  }
  if (content !== undefined) {
    if (typeof content !== "string" || content.trim() === "" || content.length > 4000) return null;
    out.content = content;
  }
  return out;
}
