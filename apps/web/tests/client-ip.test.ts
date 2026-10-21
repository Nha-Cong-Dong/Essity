import { describe, expect, it } from "vitest";

import { clientIpFrom } from "@/lib/client-ip";

function xff(value: string): Headers {
  return new Headers({ "x-forwarded-for": value });
}

describe("clientIpFrom (AC6, W4)", () => {
  it("trusts nothing when no proxy is trusted", () => {
    expect(clientIpFrom(xff("203.0.113.7"), 0)).toBeNull();
  });

  it("takes the entry the trusted proxy appended, counting from the right", () => {
    expect(clientIpFrom(xff("203.0.113.7, 198.51.100.2"), 1)).toBe("198.51.100.2");
    expect(clientIpFrom(xff("203.0.113.7, 198.51.100.2"), 2)).toBe("203.0.113.7");
  });

  it("ignores a spoofed leftmost entry", () => {
    // The client wrote "1.1.1.1"; the one proxy in front of web appended the real address.
    expect(clientIpFrom(xff("1.1.1.1, 203.0.113.7"), 1)).toBe("203.0.113.7");
  });

  it("returns nothing when there are fewer entries than trusted proxies", () => {
    expect(clientIpFrom(xff("203.0.113.7"), 2)).toBeNull();
    expect(clientIpFrom(new Headers(), 1)).toBeNull();
  });

  it("returns nothing for an entry that is not an IP address", () => {
    expect(clientIpFrom(xff("not-an-ip"), 1)).toBeNull();
    expect(clientIpFrom(xff("203.0.113.7, "), 1)).toBeNull();
  });

  it("accepts IPv6", () => {
    expect(clientIpFrom(xff("2001:db8::1"), 1)).toBe("2001:db8::1");
  });
});
