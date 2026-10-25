// Copies the build's static files next to the standalone server, as apps/web/Dockerfile does, so
// `node .next/standalone/apps/web/server.js` serves them (ADR-0025: the layout test, locally and
// in CI). Run after `pnpm build`.
import { cpSync, existsSync } from "node:fs";
import path from "node:path";

const web = path.resolve(import.meta.dirname, "..");
const source = path.join(web, ".next", "static");
const target = path.join(web, ".next", "standalone", "apps", "web", ".next", "static");

if (!existsSync(source)) {
  console.error("No .next/static: run `pnpm build` first.");
  process.exit(1);
}
cpSync(source, target, { recursive: true });
console.log(`Copied ${path.relative(web, source)} to ${path.relative(web, target)}`);
