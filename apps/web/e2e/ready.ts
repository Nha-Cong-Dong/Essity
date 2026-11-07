import type { Page } from "@playwright/test";

/**
 * Waits until the page is really there: the streamed content has replaced React's hidden
 * placeholder, React has hydrated every element in <main>, and the fonts are loaded.
 *
 * `goto` resolves on the load event, which does not wait for any of that. Under a loaded runner
 * `boundingBox()` returned null (the streamed block was still hidden), and a click landed before
 * React had attached its handlers (FIX-E2E). Never poll for this with a retry: wait for the signal.
 */
export async function settled(page: Page): Promise<void> {
  await page.waitForFunction(() => {
    const main = document.querySelector("main");
    if (!main || main.closest("[hidden]")) return false;
    const hydrated = (el: Element) => Object.keys(el).some((k) => k.startsWith("__reactFiber$"));
    // R71: a library that draws into a React element (Cytoscape's canvases) makes nodes React never
    // owns; they carry no fiber, so they are not waited for. Mark the host with data-foreign-dom.
    const ours = (el: Element) => el.closest("[data-foreign-dom]") === null || el.hasAttribute("data-foreign-dom");
    return hydrated(main) && Array.from(main.querySelectorAll("*")).filter(ours).every(hydrated);
  });
  await page.evaluate(() => document.fonts.ready);
}
