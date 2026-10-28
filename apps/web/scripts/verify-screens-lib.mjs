// Pure parts of verify-screens.mjs (arguments, uncovered routes, per-check verdict), kept apart
// so Vitest covers them without a browser or a server.

export const DEFAULT_WIDTHS = [390, 1440];

export const HELP = `Usage: pnpm verify [--route <substring>]... [--width 390,1440] [--dry-run] [--help]
Opens each screen of the standalone build in Chromium at each width and writes a JSON report and
screenshots to apps/web/.verify/. Run \`pnpm build\` and \`node scripts/prepare-standalone.mjs\` first.`;

/** Thrown for bad input; the CLI prints it as JSON with the hint. */
export class VerifyError extends Error {
  constructor(message, hint) {
    super(message);
    this.hint = hint;
  }
}

export function parseArgs(argv) {
  const args = { widths: [...DEFAULT_WIDTHS], routes: [], dryRun: false, help: false };
  for (let i = 0; i < argv.length; i += 1) {
    const [flag, inline] = argv[i].split(/=(.*)/s);
    const value = () => {
      const v = inline ?? argv[++i];
      if (v === undefined || v.startsWith("--")) {
        throw new VerifyError(`${flag} needs a value`, `Use ${flag} <value>; see --help.`);
      }
      return v;
    };
    if (flag === "--dry-run") args.dryRun = true;
    else if (flag === "--help") args.help = true;
    else if (flag === "--route") args.routes.push(value());
    else if (flag === "--width") {
      const widths = value().split(",").map((w) => Number(w.trim()));
      if (widths.some((w) => !Number.isInteger(w) || w < 200 || w > 4000)) {
        throw new VerifyError("--width must be integers between 200 and 4000", "Example: --width 390,1440");
      }
      args.widths = widths;
    } else {
      throw new VerifyError(`Unknown argument ${argv[i]}`, "Run with --help to see the flags.");
    }
  }
  return args;
}

/** URL path of a route given as segments (route groups already dropped). */
export function routePath(segments) {
  return `/${segments.join("/")}`;
}

/** Page routes (as segments) that are neither a screen nor listed as needing the backend. */
export function uncoveredRoutes(pageSegments, screenPaths, needsBackend) {
  const covered = new Set([...screenPaths, ...Object.keys(needsBackend)]);
  return pageSegments.map(routePath).filter((p) => !covered.has(p));
}

export function selectScreens(screens, filters) {
  if (filters.length === 0) return screens;
  return screens.filter((s) => filters.some((f) => s.path.includes(f)));
}

/** Verdict for one screen at one width; every failure starts with the check name. */
export function checkResult(r) {
  const failures = [];
  if (r.status !== r.expectedStatus) {
    failures.push(`status: got ${r.status}, expected ${r.expectedStatus}`);
  }
  if (new URL(r.finalUrl).pathname !== r.expectedUrl) {
    failures.push(`url: ended on ${new URL(r.finalUrl).pathname}, expected ${r.expectedUrl}`);
  }
  for (const e of r.consoleErrors) failures.push(`console: ${e}`);
  for (const e of r.pageErrors) failures.push(`pageerror: ${e}`);
  // 1 px of slack for sub-pixel rounding.
  if (r.scrollWidth > r.clientWidth + 1) {
    failures.push(`scroll: content ${r.scrollWidth}px wider than viewport ${r.clientWidth}px`);
  }
  return { ok: failures.length === 0, failures };
}
