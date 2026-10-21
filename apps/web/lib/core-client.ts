import "server-only";

import { type CoreClient, createCoreClient } from "@essity/api-client";

import { clientIpFrom } from "@/lib/client-ip";
import { webConfig } from "@/lib/config";
import { CORE_API_URL, coreFetch } from "@/lib/core";

export type { components } from "@essity/api-client";

// The only file that creates a core-api client (a test checks): every call goes through
// coreFetch, so none is cached or left without a timeout (W3).

const SERVICE_TOKEN_HEADER = "X-Service-Token";
const CLIENT_IP_HEADER = "X-Client-IP";

export type CoreAuth = {
  /** The user's session token, from the session cookie. */
  token?: string;
  /** The user's IP (W4); core-api only trusts it alongside the service token. */
  clientIp?: string | null;
};

export function coreClient({ token, clientIp }: CoreAuth = {}): CoreClient {
  return createCoreClient({
    baseUrl: CORE_API_URL,
    fetch: async (request: Request) => {
      const { serviceToken } = webConfig();
      // Built from scratch: nothing the browser sent is passed on.
      const headers = new Headers({ accept: "application/json" });
      const contentType = request.headers.get("content-type");
      if (contentType) headers.set("content-type", contentType);
      if (token) headers.set("authorization", `Bearer ${token}`);
      if (serviceToken) {
        headers.set(SERVICE_TOKEN_HEADER, serviceToken);
        if (clientIp) headers.set(CLIENT_IP_HEADER, clientIp);
      }
      const url = new URL(request.url);
      const body = request.method === "GET" ? undefined : await request.arrayBuffer();
      return coreFetch(url.pathname + url.search, {
        method: request.method,
        headers,
        body: body && body.byteLength > 0 ? body : undefined,
      });
    },
  });
}

/** A client for a route handler: the user's IP comes from the request (W4). */
export function coreClientFor(request: Request, token?: string): CoreClient {
  const clientIp = clientIpFrom(request.headers, webConfig().trustedProxyHops);
  return coreClient({ token, clientIp });
}
