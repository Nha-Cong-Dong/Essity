// @vitest-environment jsdom
// PREDEPLOY-FIX-A E-03: /subjects/[id]/syllabus logged React error #418 (hydration mismatch). The page
// is rendered to HTML on the server, then hydrated: no recoverable error, no console error.
import { act } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { hydrateRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";

import { SyllabusLive } from "@/components/syllabus/syllabus-live";
import type { OutlineOut } from "@/lib/syllabus/api";

type Section = OutlineOut["sections"][number];
const sec = (over: Partial<Section> & { id: string }): Section => ({
  parent_id: null, title: `${over.id} Phần`, first_page: 1, last_page: 10, weight: 10, unit: "page", source: "bookmark",
  excluded: false, excluded_effective: false, progress: 0, studied: false, learned: false, children: [], ...over,
});
const tree = [
  sec({ id: "1", last_page: 20, weight: 20, children: [sec({ id: "1.1" }), sec({ id: "1.2", first_page: 11, last_page: 20, studied: true })] }),
  sec({ id: "2", first_page: 21, last_page: 40, weight: 20, learned: true, excluded: true }),
];
const outline = (over: Partial<OutlineOut> = {}): OutlineOut => ({
  subject_id: "9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b", document: { id: "d1", page_count: 100, short_name: "giao_trinh_mmt.pdf" },
  progress: 0.3, reason: null, temporary: false, remaining_chapters: 1, sections: tree, ...over,
});

async function mismatches(initial: OutlineOut): Promise<string[]> {
  const element = <SyllabusLive subjectId="9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b" subjectName="Mạng" initial={initial} />;
  const container = document.createElement("div");
  container.innerHTML = renderToString(element);
  document.body.append(container);
  const found: string[] = [];
  const spy = vi.spyOn(console, "error").mockImplementation((...args) => void (/hydrat|mismatch|#418/i.test(args.map(String).join(" ")) && found.push(String(args[0]))));
  await act(async () => {
    hydrateRoot(container, element, { onRecoverableError: (error) => void found.push(String(error)) });
  });
  spy.mockRestore();
  container.remove();
  return found;
}

describe("E-03 syllabus hydration", () => {
  it("E-03 a ready outline hydrates without a mismatch", async () => {
    expect(await mismatches(outline())).toEqual([]);
  });
  it("E-03 a provisional outline hydrates without a mismatch", async () => {
    expect(await mismatches(outline({ temporary: true }))).toEqual([]);
  });
  it("E-03 the empty and waiting states hydrate without a mismatch", async () => {
    expect(await mismatches(outline({ sections: [], document: null, reason: "no_textbook" }))).toEqual([]);
    expect(await mismatches(outline({ sections: [], reason: "not_indexed" }))).toEqual([]);
  });
});
