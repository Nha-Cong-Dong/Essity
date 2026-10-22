// T1.20: what /subjects does when core-api cannot list the subjects (review c469b4d #1).
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

let failure: Error | null = null;
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw new Error(`redirect:${to}`);
  },
  notFound: () => {
    throw new Error("notFound");
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
    findSubject: async () => {
      if (failure) throw failure;
      return null;
    },
  };
});

const { CoreStatusError } = await import("@/lib/subjects");
const { Subjects, subjectForUpload } = await import("@/components/subjects/subjects-loader");

describe("/subjects when the list fails", () => {
  beforeEach(() => {
    failure = null;
  });

  it("a session core-api no longer knows goes to /login", async () => {
    failure = new CoreStatusError("/v1/subjects", 401);
    await expect(Subjects({ example: "15/12/2031" })).rejects.toThrow("redirect:/login");
  });

  it("any other failure shows the error state and logs the status only (ADR-0013)", async () => {
    const logged = vi.spyOn(console, "error").mockImplementation(() => undefined);
    failure = new CoreStatusError("/v1/subjects", 500);

    const markup = renderToStaticMarkup(await Subjects({ example: "15/12/2031" }));

    expect(markup).toContain('role="alert"');
    expect(logged).toHaveBeenCalledWith("core-api call failed", { route: "subjects", status: 500, error: "CoreStatusError" });
  });
});

describe("/subjects/[id]/upload when the list fails (review 796071c #1)", () => {
  it("a session core-api no longer knows goes to /login", async () => {
    failure = new CoreStatusError("/v1/subjects", 401);
    await expect(subjectForUpload("3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b")).rejects.toThrow("redirect:/login");
  });

  // Red when: a subject findSubject does not return (someone else's, gone, or an id that is not
  // one: all null, see subjects-lib) renders the step instead of the not-found page (plan K5).
  it("plan K5: a subject that is not found is the not-found page", async () => {
    failure = null;
    await expect(subjectForUpload("0f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b")).rejects.toThrow("notFound");
  });
});
