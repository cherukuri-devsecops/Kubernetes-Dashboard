import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api import ai, alerts, auth, events, exec as exec_api, incidents, kubernetes, logs, metrics, reports, search, traces
from app.api import health
from app.api.health import build_health_response
from app.config import Settings, get_settings
from app.services.postgres import client as postgres_client
from app.services.postgres.seed import seed_demo_incidents
from app.services.redis import client as redis_client
from app.utils.logging_config import configure_logging
from app.utils.tracing import configure_tracing, instrument_app

settings = get_settings()
configure_logging(settings.log_level, settings.log_file)
configure_tracing(settings)
logger = logging.getLogger("kubernetes-dashboard")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("starting %s in %s", settings.app_name, settings.environment)

    # Neither store is required to serve the Kubernetes and Prometheus panels, so
    # both connect best-effort and the app starts degraded if they are down.
    pool = await postgres_client.init_pool(settings)
    await redis_client.init_client(settings)
    if pool is not None:
        try:
            await seed_demo_incidents(settings)
        except Exception as exc:  # a failed seed must never block startup
            logger.warning("demo seed skipped: %s", exc)

    yield

    await redis_client.close_client()
    await postgres_client.close_pool()
    logger.info("stopping %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Stage 1 foundation API for the Kubernetes Dashboard.",
    lifespan=lifespan,
)

instrument_app(app, settings)

# Serves /metrics for the `backend` Prometheus scrape job, which the chart has
# always defined but nothing answered — leaving the target permanently down.
Instrumentator(excluded_handlers=["/metrics", "/health"]).instrument(app).expose(
    app, endpoint="/metrics", include_in_schema=False
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(kubernetes.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(incidents.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(traces.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(exec_api.router, prefix="/api")


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "status": "ready", "docs": "/docs"}


@app.get("/health", include_in_schema=False)
async def root_health(
    app_settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    return await build_health_response(app_settings)
