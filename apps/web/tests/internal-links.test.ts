// PM review 23/10 #10, T1.22 plan E3: every page web names in its source exists. Any string
// literal that looks like an app path counts (href, redirect, go, location.assign, an array of
// pages), since the old "/onboarding" sat in an assign() that a pattern for href= missed.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { LANDINGS, NEXT_PAGES } from "@/lib/landing";
import { PUBLIC_PAGES } from "@/proxy";

const WEB = path.resolve(import.meta.dirname, "..");

function files(dir: string, pattern: RegExp): string[] {
  return readdirSync(path.join(WEB, dir), { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && pattern.test(entry.name))
    .map((entry) => path.relative(WEB, path.join(entry.parentPath, entry.name)));
}

/** Each page as its URL segments: route groups "(x)" dropped, "[id]" kept to match anything. */
const PAGES = files("app", /^page\.tsx$/).map((file) =>
  path
    .dirname(path.relative("app", file))
    .split(path.sep)
    .filter((segment) => segment !== "." && !/^\(.*\)$/.test(segment)),
);

export function isPage(url: string, pages: string[][] = PAGES): boolean {
  const segments = url.split(/[?#]/)[0].split("/").filter(Boolean);
  return pages.some(
    (page) =>
      page.length === segments.length &&
      page.every((part, i) => /^\[.*\]$/.test(part) || part === segments[i]),
  );
}

/**
 * App paths written as string literals: "/x", '/x' or `/x`; not APIs, files, templates, nor a
 * path handed to core-api (coreFetch("/healthz"), client.GET("/v1/me")).
 */
export function appPaths(source: string): string[] {
  return [...source.matchAll(/(["'`])(\/[a-z][\w\-/[\]]*)\1/g)]
    .filter((match) => !/(coreFetch|\.(GET|POST|PUT|PATCH|DELETE))\(\s*$/.test(source.slice(0, match.index)))
    .map((match) => match[2])
    .filter((url) => !/^\/(api|v1|_next)\//.test(url) && !url.includes("."));
}

describe("internal links", () => {
  const SOURCES = [...files("app", /\.(ts|tsx)$/), ...files("components", /\.(ts|tsx)$/), ...files("lib", /\.(ts|tsx)$/)];

  // Red when: a literal names a page that has no page.tsx (a link to a 404, like /onboarding).
  it("every app path in app/, components/, lib/ has a page", () => {
    const dead = SOURCES.flatMap((file) =>
      appPaths(readFileSync(path.join(WEB, file), "utf-8"))
        .filter((url) => !isPage(url))
        .map((url) => `${file}: ${url}`),
    );
    expect(dead).toEqual([]);
  });

  // Red when: a public page or a landing names no page, so a page added later under that name
  // would be opened without a session, or a landing sends people to a 404.
  it.each([...PUBLIC_PAGES, ...LANDINGS, ...NEXT_PAGES])("%s has a page", (url) => {
    expect(isPage(url)).toBe(true);
  });

  // Red when: the scan misses a way a page is named, or reads an API, a file or a template as one.
  it("finds assign(), a ternary href and array items; skips APIs, anchors, other sites, templates", () => {
    expect(appPaths('window.location.assign("/onboarding")')).toEqual(["/onboarding"]);
    expect(appPaths('href={ok ? "/check-email" : "/login"}')).toEqual(["/check-email", "/login"]);
    expect(appPaths('safeNext(next, ["/subjects/new", \'/today\'])')).toEqual(["/subjects/new", "/today"]);
    expect(appPaths('"/api/x" "#a" "https://x.example/y" `/subjects/${id}` "/logo.svg"')).toEqual([]);
    expect(appPaths('coreFetch("/healthz"); core.GET("/me"); go("/today")')).toEqual(["/today"]);
  });

  it("matches a route group and a dynamic segment", () => {
    const pages = [["x"], ["subjects", "[id]"]];
    expect(isPage("/x", pages)).toBe(true);
    expect(isPage("/subjects/abc", pages)).toBe(true);
    expect(isPage("/onboarding", pages)).toBe(false);
  });
});
