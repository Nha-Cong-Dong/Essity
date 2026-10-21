// Typed client for core-api. `schema.d.ts` is generated from `openapi.json` (`just gen-api`);
// never edit either by hand.
import createClient, { type ClientOptions } from "openapi-fetch";

import type { components, paths } from "./schema";

export type { components, paths };
export type CoreClient = ReturnType<typeof createClient<paths>>;

export function createCoreClient(options: ClientOptions): CoreClient {
  return createClient<paths>(options);
}
