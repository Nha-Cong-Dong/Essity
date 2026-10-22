// T1.20: what /subjects does when core-api cannot list the subjects (review c469b4d #1).
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

let failure: Error | null = null;
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw new Error(`redirect:${to}`);
  },
}));
vi.mock("@/lib/subjects", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/subjects")>();
  return {
    ...actual,
    listSubjects: async () => {
      if (failure) throw failure;
      return [];
    },
  };
});

const { CoreStatusError } = await import("@/lib/subjects");
const { Subjects } = await import("@/components/subjects/subjects-loader");

describe("/subjects when the list fails", () => {
  beforeEach(() => {
    failure = null;
  });

  it("a session core-api no longer knows goes to /login", async () => {
    failure = new CoreStatusError("/v1/subjects", 401);
    await expect(Subjects()).rejects.toThrow("redirect:/login");
  });

  it("any other failure shows the error state and logs the status only (ADR-0013)", async () => {
    const logged = vi.spyOn(console, "error").mockImplementation(() => undefined);
    failure = new CoreStatusError("/v1/subjects", 500);

    const markup = renderToStaticMarkup(await Subjects());

    expect(markup).toContain('role="alert"');
    expect(logged).toHaveBeenCalledWith("core-api call failed", { route: "subjects", status: 500, error: "CoreStatusError" });
  });
});
