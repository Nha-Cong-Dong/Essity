// Pure parts of scripts/verify-screens.mjs: argument parsing, uncovered routes, per-check verdict.
import { createServer } from "node:net";
import type { AddressInfo } from "node:net";

import { describe, expect, it } from "vitest";

import {
  checkResult,
  isPortOpen,
  parseArgs,
  routePath,
  selectScreens,
  uncoveredRoutes,
} from "../scripts/verify-screens-lib.mjs";
import { appRoutes } from "./app-routes";

describe("parseArgs", () => {
  it("defaults to widths 390 and 1440 with no filter", () => {
    expect(parseArgs([])).toEqual({ widths: [390, 1440], routes: [], dryRun: false, help: false });
  });

  it("collects repeated --route and a --width list", () => {
    const args = parseArgs(["--route", "login", "--route=today", "--width", "320,768"]);
    expect(args).toMatchObject({ routes: ["login", "today"], widths: [320, 768] });
  });

  it("reads --dry-run and --help", () => {
    expect(parseArgs(["--dry-run", "--help"])).toMatchObject({ dryRun: true, help: true });
  });

  it("rejects a bad width and an unknown flag with a hint", () => {
    expect(() => parseArgs(["--width", "abc"])).toThrow(/--width/);
    expect(() => parseArgs(["--nope"])).toThrow(/--nope/);
    expect(() => parseArgs(["--route"])).toThrow(/--route/);
  });
});

describe("routePath", () => {
  it("turns segments into a URL path", () => {
    expect(routePath([])).toBe("/");
    expect(routePath(["design-preview", "today"])).toBe("/design-preview/today");
  });
});

describe("uncoveredRoutes", () => {
  it("lists page routes that are neither screens nor needs-backend", () => {
    const pages = [[], ["login"], ["subjects"], ["subjects", "[id]"], ["new-page"]];
    const out = uncoveredRoutes(pages, ["/", "/login"], { "/subjects": "needs session" });
    expect(out).toEqual(["/subjects/[id]", "/new-page"]);
  });

  it("covers a dynamic route listed in needs-backend by its pattern", () => {
    expect(uncoveredRoutes([["subjects", "[id]"]], [], { "/subjects/[id]": "x" })).toEqual([]);
  });

  it("matches the real app routes helper shape", () => {
    const out = uncoveredRoutes(appRoutes("page"), ["/"], {});
    expect(out).toContain("/login");
    expect(out).not.toContain("/");
  });
});

describe("isPortOpen", () => {
  it("is true while something listens on the port and false once it is closed", async () => {
    const server = createServer();
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const { port } = server.address() as AddressInfo;
    expect(await isPortOpen(port)).toBe(true);
    await new Promise((resolve) => server.close(resolve));
    expect(await isPortOpen(port)).toBe(false);
  });
});

describe("selectScreens", () => {
  const screens = [{ path: "/login" }, { path: "/design-preview/today" }];
  it("keeps all without a filter and filters by substring otherwise", () => {
    expect(selectScreens(screens, [])).toHaveLength(2);
    expect(selectScreens(screens, ["today"])).toEqual([{ path: "/design-preview/today" }]);
    expect(selectScreens(screens, ["zzz"])).toEqual([]);
  });
});

describe("checkResult", () => {
  const ok = {
    expectedStatus: 200,
    status: 200,
    expectedUrl: "/login",
    finalUrl: "http://127.0.0.1:3101/login",
    consoleErrors: [],
    pageErrors: [],
    scrollWidth: 390,
    clientWidth: 390,
  };

  it("passes when every check is fine", () => {
    expect(checkResult(ok)).toEqual({ ok: true, failures: [] });
  });

  it("flags status, redirect, console, page error and sideways scroll", () => {
    const bad = {
      ...ok,
      status: 500,
      finalUrl: "http://127.0.0.1:3101/register",
      consoleErrors: ["boom"],
      pageErrors: ["oops"],
      scrollWidth: 500,
    };
    const { ok: passed, failures } = checkResult(bad);
    expect(passed).toBe(false);
    expect(failures.map((f: string) => f.split(":")[0])).toEqual([
      "status",
      "url",
      "console",
      "pageerror",
      "scroll",
    ]);
  });

  it("allows 1 px of scroll rounding", () => {
    expect(checkResult({ ...ok, scrollWidth: 391 }).ok).toBe(true);
  });
});
