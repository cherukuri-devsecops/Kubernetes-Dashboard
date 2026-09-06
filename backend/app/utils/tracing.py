"""OTLP trace export.

The backend is the trace source for the collection layer: spans go to the OTel
Collector, which forwards them to Tempo. Every step is optional - missing
packages or an unreachable collector must never stop the API from serving.
"""

import logging

from fastapi import FastAPI

from app.config import Settings

logger = logging.getLogger("kubernetes-dashboard")

# Health and docs traffic would otherwise dominate the trace volume.
_EXCLUDED_URLS = "health,docs,redoc,openapi.json"


def configure_tracing(settings: Settings) -> None:
    if not settings.otel_enabled or not settings.otel_exporter_otlp_endpoint:
        logger.info("otel tracing disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        logger.warning("otel packages unavailable, tracing disabled: %s", exc)
        return

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.otel_service_name,
                "deployment.environment": settings.environment,
            }
        )
    )
    # The exporter connects lazily and drops spans if the collector is down, so a
    # missing collector costs nothing at startup.
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
        )
    )
    trace.set_tracer_provider(provider)
    logger.info("otel tracing exporting to %s", settings.otel_exporter_otlp_endpoint)


def instrument_app(app: FastAPI, settings: Settings) -> None:
    if not settings.otel_enabled or not settings.otel_exporter_otlp_endpoint:
        return

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError:
        return

    FastAPIInstrumentor.instrument_app(app, excluded_urls=_EXCLUDED_URLS)
