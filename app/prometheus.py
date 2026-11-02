"""Prometheus exposition: metrics are read at scrape time, never cached."""

from collections.abc import Iterator

from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, Metric
from prometheus_client.registry import Collector

from app.collectors import collect_snapshot
from app.services import check_services


class SystemCollector(Collector):
    def collect(self) -> Iterator[Metric]:
        snap = collect_snapshot()

        cpu = GaugeMetricFamily("infra_cpu_usage_percent", "CPU usage, 0-100", labels=["cpu"])
        cpu.add_metric(["total"], snap.cpu.percent)
        for i, value in enumerate(snap.cpu.per_core):
            cpu.add_metric([str(i)], value)
        yield cpu

        count = GaugeMetricFamily("infra_cpu_count", "Number of CPUs", labels=["kind"])
        count.add_metric(["logical"], snap.cpu.count_logical)
        if snap.cpu.count_physical is not None:
            count.add_metric(["physical"], snap.cpu.count_physical)
        yield count

        if snap.cpu.load_avg is not None:
            load = GaugeMetricFamily("infra_load_average", "Load average", labels=["period"])
            for period, value in zip(("1m", "5m", "15m"), snap.cpu.load_avg, strict=True):
                load.add_metric([period], value)
            yield load

        mem = GaugeMetricFamily("infra_memory_bytes", "Memory in bytes", labels=["state"])
        mem.add_metric(["total"], snap.memory.total)
        mem.add_metric(["available"], snap.memory.available)
        mem.add_metric(["used"], snap.memory.used)
        yield mem
        yield GaugeMetricFamily(
            "infra_memory_usage_percent", "Memory usage, 0-100", value=snap.memory.percent
        )

        swap = GaugeMetricFamily("infra_swap_bytes", "Swap in bytes", labels=["state"])
        swap.add_metric(["total"], snap.memory.swap_total)
        swap.add_metric(["used"], snap.memory.swap_used)
        yield swap

        disk = GaugeMetricFamily(
            "infra_disk_bytes", "Disk space in bytes", labels=["mountpoint", "state"]
        )
        disk_pct = GaugeMetricFamily(
            "infra_disk_usage_percent", "Disk usage, 0-100", labels=["mountpoint"]
        )
        for d in snap.disks:
            disk.add_metric([d.mountpoint, "total"], d.total)
            disk.add_metric([d.mountpoint, "used"], d.used)
            disk.add_metric([d.mountpoint, "free"], d.free)
            disk_pct.add_metric([d.mountpoint], d.percent)
        yield disk
        yield disk_pct

        # Counters: Prometheus adds the _total suffix and rate() works on them.
        net = CounterMetricFamily(
            "infra_network_bytes", "Network bytes", labels=["interface", "direction"]
        )
        errs = CounterMetricFamily(
            "infra_network_errors", "Network errors", labels=["interface", "direction"]
        )
        for n in snap.network:
            net.add_metric([n.interface, "sent"], n.bytes_sent)
            net.add_metric([n.interface, "recv"], n.bytes_recv)
            errs.add_metric([n.interface, "in"], n.errin)
            errs.add_metric([n.interface, "out"], n.errout)
        yield net
        yield errs

        yield GaugeMetricFamily(
            "infra_uptime_seconds", "Seconds since boot", value=snap.uptime_seconds
        )

        report = check_services()
        if report.services:
            up = GaugeMetricFamily(
                "infra_service_up", "1 if the TCP check succeeded", labels=["service", "target"]
            )
            for s in report.services:
                up.add_metric([s.name, s.target], 1.0 if s.up else 0.0)
            yield up


registry = CollectorRegistry()
registry.register(SystemCollector())


def render() -> bytes:
    return generate_latest(registry)
