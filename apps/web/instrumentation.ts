import { webConfig } from "@/lib/config";

// OpenTelemetry (ADR-0013). Next.js calls register() once per server instance.
// The tracer setup is Node-only, so it is loaded only in the Node.js runtime.
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    // R04, review plan P1: a server missing a setting stops here, naming it, rather than
    // answering 500 to its first visitor. Not during `next build`, which has none of them.
    if (process.env.NEXT_PHASE !== "phase-production-build") webConfig();
    await import("./instrumentation.node");
  }
}
