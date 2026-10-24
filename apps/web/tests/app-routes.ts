// The app's URLs as Next builds them from app/: one per page.* or route.*, route groups "(x)"
// dropped, "[id]" kept to match any segment. Shared by internal-links and removed-routes.
import { readdirSync } from "node:fs";
import path from "node:path";

const APP = path.resolve(import.meta.dirname, "..", "app");

/** Each `page.*` (or `route.*`) under app/, as its URL segments. */
export function appRoutes(kind: "page" | "route"): string[][] {
  return readdirSync(APP, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && new RegExp(`^${kind}\\.(ts|tsx|js|jsx)$`).test(entry.name))
    .map((entry) =>
      path
        .relative(APP, entry.parentPath)
        .split(path.sep)
        .filter((segment) => segment !== "" && !/^\(.*\)$/.test(segment)),
    );
}
