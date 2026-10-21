import { connection } from "next/server";

import { coreFetch } from "@/lib/core";

// T0.6: one line showing each hop is up. Shown on /design-preview.

type ServiceStatus = "ok" | "unavailable";

type Ping = { core_api: ServiceStatus; ai_service: ServiceStatus };

// Status of each hop: web → core-api → ai-service. A hop core-api could not reach is
// reported "unavailable"; when core-api itself is down, ai-service is unknown.
async function pingChain(): Promise<{ coreApi: ServiceStatus; aiService?: ServiceStatus }> {
  try {
    const response = await coreFetch("/v1/ping");
    const ping = (await response.json()) as Ping;
    return { coreApi: ping.core_api, aiService: ping.ai_service };
  } catch {
    return { coreApi: "unavailable" };
  }
}

export async function ServiceChain() {
  await connection(); // never prerender: the result depends on the services at request time
  const { coreApi, aiService } = await pingChain();
  const text =
    aiService === undefined
      ? `web → core-api: ${coreApi}`
      : `web → core-api → ai-service: ${aiService}`;
  return <p className="font-mono text-small text-ink-soft">{text}</p>;
}
