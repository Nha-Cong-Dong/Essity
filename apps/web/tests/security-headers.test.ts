// Risk register R06, ADR-0023: every page carries the security headers. Next applies every rule
// whose source matches, and for a key set twice the later rule wins (Next's headers docs), so
// the effective headers are worked out the same way here.
import { afterEach, describe, expect, it, vi } from "vitest";

import nextConfig from "@/next.config";

afterEach(() => vi.unstubAllEnvs());

async function effective(page: string, nodeEnv: string): Promise<Map<string, string>> {
  vi.stubEnv("NODE_ENV", nodeEnv);
  const rules = (await nextConfig.headers?.()) ?? [];
  const found = new Map<string, string>();
  for (const rule of rules) {
    const matches = rule.source === "/(.*)" || rule.source === page;
    if (matches) for (const { key, value } of rule.headers) found.set(key, value);
  }
  return found;
}

function directives(csp: string | undefined): Map<string, string> {
  return new Map(
    (csp ?? "")
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => [part.split(/\s+/)[0], part] as [string, string]),
  );
}

describe("security headers in production (R06)", () => {
  // Red when: headers() covers only the two token pages, as before T1.21.
  it("r06: every page is framed by nobody, sniffed by nobody, and https only", async () => {
    const headers = await effective("/subjects", "production");
    expect(headers.get("X-Frame-Options")).toBe("DENY");
    expect(headers.get("X-Content-Type-Options")).toBe("nosniff");
    expect(headers.get("Referrer-Policy")).toBe("strict-origin-when-cross-origin");
    expect(headers.get("Strict-Transport-Security")).toBe("max-age=31536000");
    expect(headers.get("Permissions-Policy")).toMatch(/camera=\(\)/);
  });

  // Red when: a directive the review asked for (P4) is missing, or eval is allowed.
  it("r06: the CSP allows the grain's data: images, no eval, and nothing outside the site", async () => {
    const csp = directives((await effective("/", "production")).get("Content-Security-Policy"));
    expect(csp.get("default-src")).toBe("default-src 'self'");
    expect(csp.get("script-src")).toBe("script-src 'self' 'unsafe-inline'");
    expect(csp.get("img-src")).toMatch(/'self' data:/);
    expect(csp.get("connect-src")).toBe("connect-src 'self'");
    expect(csp.get("frame-ancestors")).toBe("frame-ancestors 'none'");
    expect(csp.get("object-src")).toBe("object-src 'none'");
    expect(csp.get("base-uri")).toBe("base-uri 'self'");
    expect(csp.get("form-action")).toBe("form-action 'self'");
    expect([...csp.values()].join(";")).not.toMatch(/unsafe-eval|upgrade-insecure-requests/);
  });

  // Red when: the general Referrer-Policy rule comes after the token pages' rule and wins.
  it.each(["/verify-email", "/reset-password"])("r06: %s still sends no Referer", async (page) => {
    expect((await effective(page, "production")).get("Referrer-Policy")).toBe("no-referrer");
  });
});

describe("security headers in development", () => {
  // Red when: the dev server's hot reload is blocked (it evaluates code and uses a socket).
  it("allows eval and the reload socket, and pins no HSTS on localhost", async () => {
    const headers = await effective("/", "development");
    const csp = directives(headers.get("Content-Security-Policy"));
    expect(csp.get("script-src")).toMatch(/'unsafe-eval'/);
    expect(csp.get("connect-src")).toMatch(/ws:/);
    expect(headers.has("Strict-Transport-Security")).toBe(false);
  });
});
