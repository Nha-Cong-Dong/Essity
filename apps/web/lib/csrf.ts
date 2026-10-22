import type { NextRequest } from "next/server";

import { WebConfigError, webConfig } from "@/lib/config";
import { logError } from "@/lib/log";

/**
 * ADR-0014, W5: an unsafe request is ours only if the browser says it comes from our origin.
 * No Origin, or the opaque "null", is refused: browsers send it on every POST.
 */
export function isAllowedOrigin(request: Request, allowedOrigin: string): boolean {
  return request.headers.get("origin") === allowedOrigin;
}

/**
 * Wraps every unsafe route handler (POST, PUT, PATCH, DELETE). A test checks each route uses it,
 * so the check does not depend on the proxy's matcher. Also where an incomplete production
 * configuration surfaces, before the handler runs.
 */
export function withOrigin<Args extends unknown[]>(
  handler: (request: NextRequest, ...args: Args) => Promise<Response>,
): (request: NextRequest, ...args: Args) => Promise<Response> {
  return async (request, ...args) => {
    let origin: string;
    try {
      origin = webConfig().origin;
    } catch (error) {
      if (!(error instanceof WebConfigError)) throw error;
      // The message names the missing variable, never its value (lib/config.ts).
      logError(`web configuration is incomplete: ${error.message}`);
      return Response.json({ error: "misconfigured" }, { status: 500 });
    }
    if (!isAllowedOrigin(request, origin)) {
      return Response.json({ error: "forbidden_origin" }, { status: 403 });
    }
    return handler(request, ...args);
  };
}
