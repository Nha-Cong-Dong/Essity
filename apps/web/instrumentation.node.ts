import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { resourceFromAttributes } from "@opentelemetry/resources";
import { BatchSpanProcessor, NodeTracerProvider } from "@opentelemetry/sdk-trace-node";
import { ATTR_SERVICE_NAME } from "@opentelemetry/semantic-conventions";

// Next.js creates the request and fetch spans itself; this provides the provider they report to.
// Spans are exported only when OTEL_EXPORTER_OTLP_ENDPOINT is set (the Collector, which strips
// query strings from URLs, ADR-0014). Without it, trace context still propagates to core-api.
const spanProcessors = process.env.OTEL_EXPORTER_OTLP_ENDPOINT
  ? [new BatchSpanProcessor(new OTLPTraceExporter())]
  : [];

const provider = new NodeTracerProvider({
  resource: resourceFromAttributes({ [ATTR_SERVICE_NAME]: "web" }),
  spanProcessors,
});

// Global provider, AsyncLocalStorage context manager and W3C trace context propagator.
provider.register();
