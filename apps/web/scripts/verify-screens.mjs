// Opens each screen of the production build in real Chromium at each width and prints one JSON
// report (also saved with PNGs in .verify/), so an agent sees the app, not only test results.
// Run `pnpm build` and `node scripts/prepare-standalone.mjs` first. Same server env as
// playwright.config.ts, on port 3101 so it never clashes with the e2e server on 3100.
import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

import {
  checkResult,
  HELP,
  isPortOpen,
  parseArgs,
  selectScreens,
  uncoveredRoutes,
  VerifyError,
} from "./verify-screens-lib.mjs";

const web = path.resolve(import.meta.dirname, "..");
const APP = path.join(web, "app");
const SERVER = path.join(web, ".next", "standalone", "apps", "web", "server.js");
const OUT = path.join(web, ".verify");
const PORT = 3101;
const ORIGIN = `http://127.0.0.1:${PORT}`;

// `expectUrl` differs from `path` where the app redirects on purpose (no session: / -> /login).
const SCREENS = [
  { path: "/", expectUrl: "/login" },
  { path: "/login" },
  { path: "/register" },
  // Without the email the page sends the visitor back to the form on purpose.
  { path: "/check-email", expectUrl: "/register" },
  { path: "/verify-email" },
  { path: "/forgot-password" },
  { path: "/reset-password" },
  { path: "/design-preview" },
  { path: "/design-preview/subjects" },
  { path: "/design-preview/today" },
  { path: "/design-preview/today-v1" },
  { path: "/design-preview/subject" },
  { path: "/design-preview/review" },
  { path: "/design-preview/session" },
  { path: "/design-preview/practice" },
  { path: "/design-preview/stats" },
];

// Pages behind a session: without core-api they redirect to /login, so a screen check says nothing.
const NEEDS_BACKEND = {
  "/subjects": "needs a session and core-api (redirects to /login)",
  "/today": "needs a session and core-api (redirects to /login)",
  "/review": "needs a session and core-api (redirects to /login)",
  "/review/[id]": "needs a session and core-api (redirects to /login)",
  "/subjects/new": "needs a session and core-api (redirects to /login)",
  "/subjects/[id]/documents": "needs a session and core-api (redirects to /login)",
  "/subjects/[id]/upload": "needs a session and core-api (redirects to /login)",
  "/subjects/[id]/documents/[docId]": "needs a session and core-api (redirects to /login)",
  "/subjects/[id]/sessions/new": "needs a session and core-api (redirects to /login)",
};

/** Each page.* under app/, as URL segments (route groups dropped). */
function pageRoutes() {
  return readdirSync(APP, { recursive: true, withFileTypes: true })
    .filter((e) => e.isFile() && /^page\.(ts|tsx|js|jsx)$/.test(e.name))
    .map((e) =>
      path
        .relative(APP, e.parentPath)
        .split(path.sep)
        .filter((s) => s !== "" && !/^\(.*\)$/.test(s)),
    );
}

function fail(error) {
  const body =
    error instanceof VerifyError
      ? { error: error.message, hint: error.hint }
      : {
          error: error?.message ?? String(error),
          hint: "Unexpected error; re-run, and if it repeats read the message above.",
        };
  console.log(JSON.stringify(body, null, 2));
  process.exitCode = 1;
}

function startServer() {
  const child = spawn(process.execPath, [SERVER], {
    cwd: web,
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      PORT: String(PORT),
      HOSTNAME: "127.0.0.1",
      NODE_ENV: "production",
      WEB_DESIGN_PREVIEW: "1",
      WEB_ORIGIN: ORIGIN,
      // Throwaway, made per run: nothing calls core-api here (port 9 refuses at once).
      WEB_TO_CORE_TOKEN: randomBytes(24).toString("hex"),
      WEB_TRUSTED_PROXY_HOPS: "0",
      CORE_API_URL: "http://127.0.0.1:9",
    },
  });
  let log = "";
  child.stdout.on("data", (d) => (log += d));
  child.stderr.on("data", (d) => (log += d));
  const exited = new Promise((resolve) => child.on("exit", () => resolve("exited")));
  return { child, exited, log: () => log.slice(-800) };
}

async function waitReady(server) {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${ORIGIN}/login`, { redirect: "manual" });
      if (res.status < 500) return;
    } catch {
      // not listening yet
    }
    const state = await Promise.race([server.exited, new Promise((r) => setTimeout(() => r("wait"), 300))]);
    if (state === "exited") {
      throw new VerifyError(
        `Server exited early: ${server.log()}`,
        `Is port ${PORT} free? Rebuild: pnpm build && node scripts/prepare-standalone.mjs`,
      );
    }
  }
  throw new VerifyError(
    `Server not ready in 60 s: ${server.log()}`,
    "Rebuild: pnpm build && node scripts/prepare-standalone.mjs",
  );
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log(HELP);
    return;
  }
  const screens = selectScreens(SCREENS, args.routes);
  const uncovered = uncoveredRoutes(
    pageRoutes(),
    SCREENS.map((s) => s.path),
    NEEDS_BACKEND,
  );
  if (args.dryRun) {
    const plan = { dryRun: true, origin: ORIGIN, widths: args.widths, screens, needsBackend: NEEDS_BACKEND, uncovered };
    console.log(JSON.stringify(plan, null, 2));
    return;
  }
  if (screens.length === 0) {
    throw new VerifyError(`No screen matches ${args.routes.join(", ")}`, "Run with --dry-run to list the screens.");
  }
  if (!existsSync(SERVER) || !existsSync(path.join(path.dirname(SERVER), ".next", "static"))) {
    throw new VerifyError(
      "No standalone build",
      "Run `pnpm build` and `node scripts/prepare-standalone.mjs` in apps/web, then retry.",
    );
  }
  // Loaded late so --help and --dry-run need no browser.
  const { chromium } = await import("@playwright/test");

  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(OUT, { recursive: true });
  // A server left on the port would answer in place of ours and the new one would die silently.
  if (await isPortOpen(PORT)) {
    throw new VerifyError(`Port ${PORT} is already in use`, `Stop the process holding port ${PORT}, then run again.`);
  }
  const server = startServer();
  const stop = () => server.child.kill();
  process.on("SIGINT", () => (stop(), process.exit(130)));
  process.on("SIGTERM", () => (stop(), process.exit(143)));
  let browser;
  try {
    await waitReady(server);
    try {
      browser = await chromium.launch();
    } catch (e) {
      throw new VerifyError(
        `Chromium failed to start: ${e.message.split("\n")[0]}`,
        "Run `pnpm exec playwright install chromium`, then retry.",
      );
    }
    const results = [];
    for (const screen of screens) {
      for (const width of args.widths) {
        const context = await browser.newContext({ viewport: { width, height: 900 } });
        const page = await context.newPage();
        const consoleErrors = [];
        const pageErrors = [];
        page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
        page.on("pageerror", (e) => pageErrors.push(e.message));
        const response = await page.goto(ORIGIN + screen.path, { waitUntil: "load" }).catch((e) => {
          pageErrors.push(`navigation: ${e.message.split("\n")[0]}`);
          return null;
        });
        await page.evaluate(() => document.fonts.ready);
        const { scrollWidth, clientWidth } = await page.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        }));
        const name = screen.path === "/" ? "root" : screen.path.slice(1).replaceAll("/", "_");
        const shot = `${name}-${width}.png`;
        await page.screenshot({ path: path.join(OUT, shot), fullPage: true });
        const verdict = checkResult({
          expectedStatus: 200,
          status: response?.status() ?? 0,
          expectedUrl: screen.expectUrl ?? screen.path,
          finalUrl: page.url(),
          consoleErrors,
          pageErrors,
          scrollWidth,
          clientWidth,
        });
        results.push({ route: screen.path, width, ...verdict, screenshot: `.verify/${shot}` });
        await context.close();
      }
    }
    const failed = results.filter((r) => !r.ok);
    const report = {
      ok: failed.length === 0,
      screens: screens.length,
      widths: args.widths,
      checks: results.length,
      failed: failed.length,
      results,
      uncovered,
      needsBackend: NEEDS_BACKEND,
      hint: failed.length
        ? "Open the screenshots of the failed rows in apps/web/.verify/, fix, rebuild, rerun with --route <path>."
        : undefined,
    };
    writeFileSync(path.join(OUT, "report.json"), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
    if (failed.length) process.exitCode = 1;
  } finally {
    await browser?.close();
    stop();
  }
}

main().catch(fail);
