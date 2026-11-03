import type { CoreClient } from "@/lib/core-client";

// T1.23 adds GET /v1/auth/username-available?username= -> { available, reason }. Until L1 pushes
// it and api-client is regenerated, the path is not in the typed client: this one adapter calls it
// anyway. When the path is typed, replace `loose` by `client.GET(...)` and delete this comment.
export type Availability = { available: boolean; reason: string | null };

type Loose = {
  GET: (path: string, init: { params: { query: { username: string } } }) => Promise<{ data?: unknown; response: Response }>;
};

export async function checkUsernameAvailable(client: CoreClient, username: string): Promise<Response | Availability> {
  const loose = client as unknown as Loose;
  const { data, response } = await loose.GET("/v1/auth/username-available", { params: { query: { username } } });
  if (!response.ok) return response;
  const body = data as { available?: unknown; reason?: unknown } | undefined;
  if (typeof body?.available !== "boolean") return response;
  return { available: body.available, reason: typeof body.reason === "string" ? body.reason : null };
}
