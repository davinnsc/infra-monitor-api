"""TCP health checks for the services this host depends on.

Configured with an environment variable, for example:

    INFRA_MONITOR_SERVICES="postgres=db:5432,redis=cache:6379"
    INFRA_MONITOR_CHECK_TIMEOUT=1.0
"""

import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.models import ServicesReport, ServiceStatus


@dataclass(frozen=True)
class ServiceTarget:
    name: str
    host: str
    port: int

    @property
    def target(self) -> str:
        return f"{self.host}:{self.port}"


def parse_services(raw: str) -> list[ServiceTarget]:
    """Parse "name=host:port,name2=host2:port2". Raises ValueError on bad input."""
    targets: list[ServiceTarget] = []
    for item in filter(None, (part.strip() for part in raw.split(","))):
        name, sep, address = item.partition("=")
        host, colon, port = address.rpartition(":")
        if not sep or not colon or not name.strip() or not host.strip():
            raise ValueError(f"Invalid service entry {item!r}: expected name=host:port")
        if not port.isdigit() or not 0 < int(port) < 65536:
            raise ValueError(f"Invalid port in {item!r}")
        targets.append(ServiceTarget(name.strip(), host.strip(), int(port)))
    return targets


def configured_services() -> list[ServiceTarget]:
    return parse_services(os.environ.get("INFRA_MONITOR_SERVICES", ""))


def check_timeout() -> float:
    return float(os.environ.get("INFRA_MONITOR_CHECK_TIMEOUT", "1.0"))


def check_one(svc: ServiceTarget, timeout: float) -> ServiceStatus:
    start = time.perf_counter()
    try:
        with socket.create_connection((svc.host, svc.port), timeout=timeout):
            latency = (time.perf_counter() - start) * 1000
        return ServiceStatus(
            name=svc.name, target=svc.target, up=True, latency_ms=round(latency, 2), error=None
        )
    except OSError as exc:
        return ServiceStatus(
            name=svc.name, target=svc.target, up=False, latency_ms=None, error=str(exc) or "error"
        )


def check_services(targets: list[ServiceTarget] | None = None) -> ServicesReport:
    targets = configured_services() if targets is None else targets
    if not targets:
        return ServicesReport(status="ok", services=[])
    timeout = check_timeout()
    # In parallel: the slowest dead service costs one timeout, not one per service.
    with ThreadPoolExecutor(max_workers=min(len(targets), 16)) as pool:
        results = list(pool.map(lambda s: check_one(s, timeout), targets))
    status = "ok" if all(r.up for r in results) else "degraded"
    return ServicesReport(status=status, services=results)
