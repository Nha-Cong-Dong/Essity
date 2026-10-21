// Rules checked on the source itself: each one guards against a route or page added later.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { isDesignPreview } from "@/lib/design-preview";
import { PUBLIC_PAGES } from "@/proxy";

const WEB = path.resolve(import.meta.dirname, "..");

function sourceFiles(dir: string): string[] {
  return readdirSync(path.join(WEB, dir), { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && /\.(ts|tsx)$/.test(entry.name))
    .map((entry) => path.relative(WEB, path.join(entry.parentPath, entry.name)));
}

const SOURCES = [...sourceFiles("app"), ...sourceFiles("lib"), ...sourceFiles("components"), "proxy.ts"];

function read(file: string): string {
  return readFileSync(path.join(WEB, file), "utf-8");
}

describe("source rules", () => {
  it("finds the sources it checks", () => {
    expect(SOURCES).toContain(path.join("app", "api", "auth", "login", "route.ts"));
  });

  it("ADR-0014 CSRF: every unsafe method of every API route goes through withOrigin (review plan #2)", () => {
    const routes = sourceFiles("app/api").filter((file) => path.basename(file) === "route.ts");
    const unwrapped = routes.flatMap((file) =>
      [...read(file).matchAll(/export\s+(?:async\s+)?(?:function|const)\s+(POST|PUT|PATCH|DELETE)\b(.*)/g)]
        .filter((match) => !/^\s*=\s*withOrigin\(/.test(match[2]))
        .map((match) => `${file}: ${match[1]}`),
    );
    expect(unwrapped).toEqual([]);
  });

  it("ADR-0014 CSRF: no route exports an unsafe method by re-export, which the scan above misses (review 987ad20 #2)", () => {
    const routes = sourceFiles("app/api").filter((file) => path.basename(file) === "route.ts");
    const reexports = routes.filter((file) =>
      [...read(file).matchAll(/export\s*(\*|\{[^}]*\})/g)].some(
        (match) => match[1] === "*" || /\b(POST|PUT|PATCH|DELETE)\b/.test(match[1]),
      ),
    );
    expect(reexports).toEqual([]);
  });

  it("review plan #2: no Server Actions, which bypass the origin check of /api", () => {
    const actions = SOURCES.filter((file) => /^\s*["']use server["']/m.test(read(file)));
    expect(actions).toEqual([]);
  });

  it("W3: nothing that touches a session is cached across requests (review plan #3)", () => {
    const cached = SOURCES.filter((file) => {
      const source = read(file);
      return (
        /["']use cache/.test(source) ||
        /\bunstable_cache\b/.test(source) ||
        (/@\/lib\/(session|core-client)/.test(source) && /\bcacheLife\b|\bcacheTag\b/.test(source))
      );
    });
    expect(cached).toEqual([]);
  });

  it("W3: core-api is only called through lib/core-client.ts (review 57e3969 #1)", () => {
    const direct = SOURCES.filter(
      (file) => file !== path.join("lib", "core-client.ts") && read(file).includes("@essity/api-client"),
    );
    expect(direct).toEqual([]);
  });
  it("every private page asks core-api for the session (review cdbaa25 #2)", () => {
    // The proxy only sees that a cookie exists; any value passes it.
    const pages = sourceFiles("app").filter((file) => path.basename(file) === "page.tsx");
    const route = (file: string) =>
      "/" + path.dirname(file).split(path.sep).slice(1).join("/");
    const unchecked = pages.filter((file) => {
      // /design-preview has a gate of its own in proxy.ts, before any cookie (lib/design-preview.ts).
      if (PUBLIC_PAGES.has(route(file)) || route(file) === "/" || isDesignPreview(route(file))) return false;
      return !/\brequire(Verified)?Session\(/.test(read(file));
    });
    expect(pages.length).toBeGreaterThan(2);
    expect(unchecked).toEqual([]);
  });
});
