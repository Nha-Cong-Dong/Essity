import { connection } from "next/server";
import { Suspense } from "react";

import { coreFetch } from "@/lib/core";

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

async function ServiceChain() {
  await connection(); // never prerender: the result depends on the services at request time
  const { coreApi, aiService } = await pingChain();
  const text =
    aiService === undefined
      ? `web → core-api: ${coreApi}`
      : `web → core-api → ai-service: ${aiService}`;
  return <p className="font-mono text-sm">{text}</p>;
}

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
      <h1 className="text-2xl font-semibold">Essity</h1>
      <Suspense fallback={<p className="font-mono text-sm">web → …</p>}>
        <ServiceChain />
      </Suspense>
    </main>
  );
}
