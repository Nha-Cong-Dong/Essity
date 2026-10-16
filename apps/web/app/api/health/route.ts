import { connection } from "next/server";

import { coreFetch } from "@/lib/core";

type ServiceStatus = "ok" | "unavailable";

async function coreApiStatus(): Promise<ServiceStatus> {
  try {
    const response = await coreFetch("/healthz");
    return response.ok ? "ok" : "unavailable";
  } catch {
    return "unavailable";
  }
}

export async function GET() {
  await connection(); // never prerender: the result depends on core-api at request time
  const coreApi = await coreApiStatus();
  return Response.json({ web: "ok", coreApi }, { status: coreApi === "ok" ? 200 : 503 });
}
