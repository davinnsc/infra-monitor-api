from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST

from app import __version__, prometheus
from app.collectors import collect_snapshot, prime_cpu_counters
from app.models import ServicesReport, SystemSnapshot
from app.services import check_services, configured_services


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configured_services()  # fail fast on a malformed INFRA_MONITOR_SERVICES
    prime_cpu_counters()
    yield


app = FastAPI(
    title="infra-monitor-api",
    version=__version__,
    description="Host metrics as JSON and Prometheus, plus TCP health checks.",
    lifespan=lifespan,
)


@app.get("/", tags=["meta"])
def index() -> dict:
    return {
        "name": "infra-monitor-api",
        "version": __version__,
        "endpoints": ["/health", "/metrics/system", "/health/services", "/metrics", "/docs"],
    }


@app.get("/health", tags=["health"])
def health() -> dict:
    """Liveness: the process is up and answering."""
    return {"status": "ok"}


@app.get("/metrics/system", response_model=SystemSnapshot, tags=["metrics"])
def system_metrics() -> SystemSnapshot:
    """CPU, memory, disks and network of the host, as JSON."""
    return collect_snapshot()


@app.get(
    "/health/services",
    response_model=ServicesReport,
    tags=["health"],
    responses={503: {"model": ServicesReport, "description": "At least one service is down"}},
)
def services_health() -> JSONResponse:
    """TCP check of every service in INFRA_MONITOR_SERVICES. 503 if any is down."""
    report = check_services()
    code = 200 if report.status == "ok" else 503
    return JSONResponse(report.model_dump(), status_code=code)


@app.get("/metrics", tags=["metrics"], response_class=Response)
def prometheus_metrics() -> Response:
    """Prometheus text exposition format."""
    return Response(content=prometheus.render(), media_type=CONTENT_TYPE_LATEST)
