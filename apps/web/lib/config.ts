// web's own settings (ADR-0022). Read on each request, never at module load: `next build` runs
// with NODE_ENV=production and has none of them.

const MIN_SERVICE_TOKEN_LENGTH = 32; // same floor as core-api's CORE_WEB_TOKEN

export class WebConfigError extends Error {}

export type WebConfig = {
  /** The one origin a browser may send unsafe requests from (W5). */
  origin: string;
  /** Proves to core-api that a request comes from web, so it trusts X-Client-IP. */
  serviceToken: string | undefined;
  /** Proxies in front of web that append to X-Forwarded-For; 0 = web is reached directly. */
  trustedProxyHops: number;
  /** core-api, never exposed to the internet (ARCH §3); only the web server calls it. */
  coreApiUrl: string;
};

type Env = Record<string, string | undefined>;

export function webConfig(env: Env = process.env): WebConfig {
  const production = env.NODE_ENV === "production";

  const origin = env.WEB_ORIGIN ?? (production ? undefined : "http://localhost:3000");
  if (origin === undefined) throw new WebConfigError("WEB_ORIGIN is required in production");

  const serviceToken = env.WEB_TO_CORE_TOKEN || undefined;
  if (serviceToken !== undefined && serviceToken.length < MIN_SERVICE_TOKEN_LENGTH) {
    throw new WebConfigError("WEB_TO_CORE_TOKEN is too short");
  }
  if (production && serviceToken === undefined) {
    throw new WebConfigError("WEB_TO_CORE_TOKEN is required in production");
  }

  // Production must say how many proxies it trusts: forgetting would put every user behind one
  // IP, so a few wrong passwords would lock everyone out (review plan #1).
  const hops = env.WEB_TRUSTED_PROXY_HOPS ?? (production ? undefined : "0");
  if (hops === undefined) throw new WebConfigError("WEB_TRUSTED_PROXY_HOPS is required in production");
  if (!/^\d+$/.test(hops)) throw new WebConfigError("WEB_TRUSTED_PROXY_HOPS must be a whole number");
  const trustedProxyHops = Number(hops);
  // core-api ignores X-Client-IP without the token.
  if (trustedProxyHops > 0 && serviceToken === undefined) {
    throw new WebConfigError("WEB_TRUSTED_PROXY_HOPS needs WEB_TO_CORE_TOKEN");
  }

  // R04: required in production, where 127.0.0.1 would silently be a different machine.
  const coreApiUrl = env.CORE_API_URL || (production ? undefined : "http://127.0.0.1:8000");
  if (coreApiUrl === undefined) throw new WebConfigError("CORE_API_URL is required in production");
  if (!/^https?:\/\//.test(coreApiUrl)) throw new WebConfigError("CORE_API_URL must be an http(s) URL");

  return { origin: new URL(origin).origin, serviceToken, trustedProxyHops, coreApiUrl };
}
