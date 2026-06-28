"""
K8s Observability Backend API — FastAPI entry point.

Accepts Kubernetes credentials from the ui-service via request headers:
  X-Auth-Mode       : kubeconfig | token | incluster | local
  X-Kubeconfig-B64  : base64-encoded kubeconfig YAML
  X-K8s-Token       : bearer token (token mode)
  X-K8s-Server      : API server URL (token mode)
  X-K8s-Context     : active context name
"""
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

# ── OpenTelemetry (no-op when OTEL_EXPORTER_OTLP_ENDPOINT is unset) ──────────
_otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
if _otel_endpoint:
    try:
        from opentelemetry import trace as _otel_trace
        from opentelemetry.sdk.trace import TracerProvider as _TP
        from opentelemetry.sdk.trace.export import BatchSpanProcessor as _BSP
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as _OE
        _provider = _TP()
        _provider.add_span_processor(_BSP(_OE(endpoint=_otel_endpoint, insecure=True)))
        _otel_trace.set_tracer_provider(_provider)
    except Exception as _otel_err:
        print(f"[otel] init failed (non-fatal): {_otel_err}", file=sys.stderr)

# Starlette compat fix: _IncludedRouter objects (created by include_router)
# lack a 'path' attribute and crash the instrumentator middleware route lookup.
try:
    import prometheus_fastapi_instrumentator.routing as _pfi_routing
    _orig_get_route_name = _pfi_routing._get_route_name

    def _safe_get_route_name(scope, routes):
        return _orig_get_route_name(scope, [r for r in routes if hasattr(r, "path")])

    _pfi_routing._get_route_name = _safe_get_route_name
except Exception:
    pass

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="[%(asctime)s] %(levelname)-7s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

from .routers import clusters, nodes, pods, deployments, logs, events, metrics, traces, rbac, query, raw, resources, streaming


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .pollers import start_pollers
    task = asyncio.create_task(start_pollers())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="K8s Observability Backend",
    version="1.0.0",
    description="REST API aggregating Kubernetes, Prometheus, Loki and trace backends.",
    lifespan=lifespan,
)

UI_ORIGIN = os.environ.get("UI_ORIGIN", "http://localhost:5002")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[UI_ORIGIN, "http://localhost:5000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

for _router in (clusters.router, nodes.router, pods.router, deployments.router,
                logs.router, events.router, metrics.router, traces.router,
                rbac.router, query.router, raw.router, resources.router,
                streaming.router):
    app.include_router(_router)

Instrumentator().instrument(app).expose(app)

if _otel_endpoint:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor as _FAI
        _FAI.instrument_app(app)
    except Exception as _otel_err:
        print(f"[otel] fastapi instrumentation failed (non-fatal): {_otel_err}", file=sys.stderr)


@app.get("/health")
def health():
    import time as _time
    import requests as _req

    loki_url       = os.environ.get("LOKI_URL", "http://loki:3100").rstrip("/")
    prometheus_url = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090").rstrip("/")

    def _probe(url: str) -> dict:
        t0 = _time.monotonic()
        try:
            r = _req.get(url, timeout=4)
            return {"status": "up" if r.status_code < 400 else "degraded",
                    "latency_ms": round((_time.monotonic() - t0) * 1000),
                    "code": r.status_code}
        except Exception as e:
            return {"status": "down",
                    "latency_ms": round((_time.monotonic() - t0) * 1000),
                    "error": str(e)[:120]}

    import concurrent.futures as _cf
    with _cf.ThreadPoolExecutor(max_workers=2) as pool:
        loki_fut  = pool.submit(_probe, f"{loki_url}/ready")
        prom_fut  = pool.submit(_probe, f"{prometheus_url}/-/healthy")
        loki_res  = loki_fut.result()
        prom_res  = prom_fut.result()

    services = {
        "backend":    {"status": "up", "latency_ms": 0},
        "loki":       loki_res,
        "prometheus": prom_res,
    }
    overall = ("up" if all(v["status"] == "up" for v in services.values())
               else "degraded" if any(v["status"] == "up" for v in services.values())
               else "down")
    return {"status": overall, "services": services}


@app.get("/")
def root():
    return {"service": "k8s-backend", "docs": "/docs"}
