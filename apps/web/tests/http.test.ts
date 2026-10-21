import { describe, expect, it } from "vitest";

import nextConfig from "@/next.config";
import { readStrings } from "@/lib/http";

function post(body: string) {
  return new Request("http://localhost:3000/api/auth/login", { method: "POST", body });
}

describe("readStrings (review cdbaa25 #3)", () => {
  it("reads the named string fields", async () => {
    expect(await readStrings(post('{"email":"a@example.com","x":1}'), ["email"])).toEqual({
      email: "a@example.com",
    });
  });

  it("refuses a body over 8 KB without reading it all", async () => {
    const big = JSON.stringify({ email: "a@example.com", password: "x".repeat(9000) });
    expect(await readStrings(post(big), ["email", "password"])).toBeNull();
  });

  it.each(["not json", "[]", '{"email":1}', ""])("refuses %j", async (body) => {
    expect(await readStrings(post(body), ["email"])).toBeNull();
  });
});

describe("next.config headers (PLAN T1.13 note, review T1.7b)", () => {
  it.each(["/verify-email", "/reset-password"])(
    "%s sends no Referer, so the token in its URL goes nowhere",
    async (page) => {
      const rules = (await nextConfig.headers?.()) ?? [];
      const rule = rules.find((r) => r.source === page);
      expect(rule?.headers).toContainEqual({ key: "Referrer-Policy", value: "no-referrer" });
    },
  );
});
