import socket

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import parse_services


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("INFRA_MONITOR_SERVICES", raising=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def listening_port():
    """A real TCP port with something listening on it."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    yield srv.getsockname()[1]
    srv.close()


@pytest.fixture
def closed_port():
    """A port that was free a moment ago and has nothing listening now."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_index_lists_endpoints(client):
    assert "/metrics/system" in client.get("/").json()["endpoints"]


def test_system_metrics_shape_and_ranges(client):
    body = client.get("/metrics/system").json()
    assert 0 <= body["cpu"]["percent"] <= 100
    assert body["cpu"]["count_logical"] >= 1
    assert len(body["cpu"]["per_core"]) == body["cpu"]["count_logical"]
    assert body["memory"]["total"] > 0
    assert 0 <= body["memory"]["percent"] <= 100
    assert body["disks"], "at least one readable disk"
    for d in body["disks"]:
        assert d["total"] >= d["used"]
    assert body["uptime_seconds"] > 0


def test_prometheus_exposition(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    text = r.text
    for name in (
        'infra_cpu_usage_percent{cpu="total"}',
        'infra_memory_bytes{state="total"}',
        "infra_memory_usage_percent",
        "infra_disk_usage_percent",
        "infra_network_bytes_total",
        "infra_uptime_seconds",
    ):
        assert name in text, name
    assert "infra_service_up" not in text  # no services configured


def test_services_empty_is_ok(client):
    r = client.get("/health/services")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "services": []}


def test_service_up(client, monkeypatch, listening_port):
    monkeypatch.setenv("INFRA_MONITOR_SERVICES", f"local=127.0.0.1:{listening_port}")
    r = client.get("/health/services")
    assert r.status_code == 200
    svc = r.json()["services"][0]
    assert svc["up"] is True
    assert svc["latency_ms"] is not None
    assert 'infra_service_up{service="local"' in client.get("/metrics").text


def test_service_down_returns_503(client, monkeypatch, listening_port, closed_port):
    monkeypatch.setenv("INFRA_MONITOR_CHECK_TIMEOUT", "0.5")
    monkeypatch.setenv(
        "INFRA_MONITOR_SERVICES",
        f"up=127.0.0.1:{listening_port},down=127.0.0.1:{closed_port}",
    )
    r = client.get("/health/services")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    by_name = {s["name"]: s for s in body["services"]}
    assert by_name["up"]["up"] is True
    assert by_name["down"]["up"] is False
    assert by_name["down"]["error"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", []),
        ("db=localhost:5432", [("db", "localhost", 5432)]),
        (" a=h1:1 , b=h2:65535 ,", [("a", "h1", 1), ("b", "h2", 65535)]),
    ],
)
def test_parse_services_valid(raw, expected):
    assert [(s.name, s.host, s.port) for s in parse_services(raw)] == expected


@pytest.mark.parametrize(
    "raw", ["db", "db=localhost", "=localhost:1", "db=:5432", "db=h:0", "db=h:70000", "db=h:abc"]
)
def test_parse_services_invalid(raw):
    with pytest.raises(ValueError):
        parse_services(raw)
