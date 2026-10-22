import { describe, expect, it } from "vitest";

import { WebConfigError, webConfig } from "@/lib/config";

const TOKEN = "web-token-for-tests-only-0123456789";

describe("webConfig (ADR-0022)", () => {
  it("defaults to localhost and no proxy outside production", () => {
    expect(webConfig({ NODE_ENV: "development" })).toEqual({
      origin: "http://localhost:3000",
      serviceToken: undefined,
      trustedProxyHops: 0,
      coreApiUrl: "http://127.0.0.1:8000",
    });
  });

  it("normalises WEB_ORIGIN to an origin", () => {
    expect(webConfig({ WEB_ORIGIN: "https://essity.example/some/path" }).origin).toBe(
      "https://essity.example",
    );
  });

  it("refuses a short service token", () => {
    expect(() => webConfig({ WEB_TO_CORE_TOKEN: "short" })).toThrow(WebConfigError);
  });

  it("refuses hops that are not a whole number", () => {
    for (const hops of ["-1", "1.5", "two"]) {
      expect(() => webConfig({ WEB_TRUSTED_PROXY_HOPS: hops, WEB_TO_CORE_TOKEN: TOKEN })).toThrow(
        WebConfigError,
      );
    }
  });

  it("W4: trusting a proxy without the service token is a configuration error", () => {
    // core-api ignores X-Client-IP without the token, so every user would share one IP.
    expect(() => webConfig({ WEB_TRUSTED_PROXY_HOPS: "1" })).toThrow(WebConfigError);
  });

  describe("production fails closed (review plan #1)", () => {
    const production = {
      NODE_ENV: "production",
      WEB_ORIGIN: "https://essity.example",
      WEB_TO_CORE_TOKEN: TOKEN,
      WEB_TRUSTED_PROXY_HOPS: "1",
      CORE_API_URL: "http://core-api:8000",
    };

    it("accepts a complete configuration", () => {
      expect(webConfig(production)).toEqual({
        origin: "https://essity.example",
        serviceToken: TOKEN,
        trustedProxyHops: 1,
        coreApiUrl: "http://core-api:8000",
      });
    });

    // R04: CORE_API_URL too; it used to fall back to 127.0.0.1 silently (lib/core.ts).
    it.each(["WEB_ORIGIN", "WEB_TO_CORE_TOKEN", "WEB_TRUSTED_PROXY_HOPS", "CORE_API_URL"])(
      "refuses a missing %s, naming it",
      (name) => {
        const env: Record<string, string | undefined> = { ...production, [name]: undefined };
        expect(() => webConfig(env)).toThrow(new RegExp(name));
      },
    );

    it("r04: an empty CORE_API_URL (Compose's unset variable) is missing too", () => {
      expect(() => webConfig({ ...production, CORE_API_URL: "" })).toThrow(/CORE_API_URL/);
    });

    it("r04: CORE_API_URL must be an http(s) URL", () => {
      for (const url of ["core-api:8000", "http://", "ftp://core-api"]) {
        expect(() => webConfig({ ...production, CORE_API_URL: url })).toThrow(/CORE_API_URL/);
      }
    });

    it("accepts hops = 0 only when set explicitly (web reached directly, as in Compose)", () => {
      expect(webConfig({ ...production, WEB_TRUSTED_PROXY_HOPS: "0" }).trustedProxyHops).toBe(0);
    });
  });
});
