// OpenTelemetry (ADR-0013). Next.js calls register() once per server instance.
// The tracer setup is Node-only, so it is loaded only in the Node.js runtime.
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./instrumentation.node");
  }
}
