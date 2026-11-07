// AUTH-V4: each call site picks the right mascot. Sun = the encourager (praise, done, auth); cloud =
// the assistant (empty, waiting, hints; the default). Red when a praise screen drops the sun or an
// empty state takes it. Source-level because the screens need a session or API to render.
import { readFileSync } from "node:fs";
import path from "node:path";

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Mascot } from "@/components/mascot";

const src = (file: string) => readFileSync(path.resolve(import.meta.dirname, "..", file), "utf8");
const mascotTags = (file: string) => src(file).match(/<Mascot\b[^>]*>/g) ?? [];

describe("Mascot kind at call sites", () => {
  it.each([
    "components/session-study/session-saved.tsx",
    "components/auth/auth-layout.tsx",
  ])("%s uses the sun only", (file) => {
    const tags = mascotTags(file);
    expect(tags.length).toBeGreaterThan(0);
    for (const t of tags) expect(t).toContain('kind="sun"');
  });

  it("the end-of-session pop-up cheers with the sun and waits with the cloud", () => {
    const [tag] = mascotTags("components/session-study/session-end-dialog.tsx");
    expect(tag).toContain('kind={empty ? undefined : "sun"}');
    expect(tag).toContain('pose={empty ? "cho" : "khen"}');
  });

  it.each([
    "components/empty-state.tsx",
    "components/screen-kit.tsx",
    "components/today-v2/today-v2-screen.tsx",
    "components/stats/stats-screen.tsx",
    "components/subjects/subject-list.tsx",
  ])("%s keeps the cloud (default) for empty and waiting states", (file) => {
    for (const t of mascotTags(file)) expect(t).not.toContain('kind="sun"');
  });

  it("renders the kind it is given, cloud by default", () => {
    expect(renderToStaticMarkup(<Mascot pose="khen" />)).toContain('data-mascot-kind="cloud"');
    expect(renderToStaticMarkup(<Mascot pose="khen" kind="sun" />)).toContain('data-mascot-kind="sun"');
  });
});
