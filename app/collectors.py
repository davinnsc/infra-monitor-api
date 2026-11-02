"""Reads host metrics with psutil and returns them as typed snapshots."""

import platform
import socket
import time

import psutil

from app.models import CpuInfo, DiskInfo, MemoryInfo, NetworkInfo, SystemSnapshot


def prime_cpu_counters() -> None:
    """psutil.cpu_percent(interval=None) compares against the previous call.

    The very first call always returns 0.0, so call it once at startup and the
    first real request already gets a meaningful number.
    """
    psutil.cpu_percent(interval=None)
    psutil.cpu_percent(interval=None, percpu=True)


def collect_cpu() -> CpuInfo:
    try:
        load_avg = [round(x, 2) for x in psutil.getloadavg()]
    except (AttributeError, OSError):
        load_avg = None
    return CpuInfo(
        percent=psutil.cpu_percent(interval=None),
        per_core=psutil.cpu_percent(interval=None, percpu=True),
        count_logical=psutil.cpu_count(logical=True) or 0,
        count_physical=psutil.cpu_count(logical=False),
        load_avg=load_avg,
    )


def collect_memory() -> MemoryInfo:
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    return MemoryInfo(
        total=vm.total,
        available=vm.available,
        used=vm.used,
        percent=vm.percent,
        swap_total=sw.total,
        swap_used=sw.used,
        swap_percent=sw.percent,
    )


def collect_disks() -> list[DiskInfo]:
    disks: list[DiskInfo] = []
    seen: set[str] = set()
    for part in psutil.disk_partitions(all=False):
        if not part.fstype or part.mountpoint in seen:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            # Empty card readers, CD drives, mounts we cannot read: skip, do not fail.
            continue
        seen.add(part.mountpoint)
        disks.append(
            DiskInfo(
                mountpoint=part.mountpoint,
                fstype=part.fstype,
                total=usage.total,
                used=usage.used,
                free=usage.free,
                percent=usage.percent,
            )
        )
    return disks


def collect_network() -> list[NetworkInfo]:
    return [
        NetworkInfo(
            interface=name,
            bytes_sent=c.bytes_sent,
            bytes_recv=c.bytes_recv,
            packets_sent=c.packets_sent,
            packets_recv=c.packets_recv,
            errin=c.errin,
            errout=c.errout,
        )
        for name, c in sorted(psutil.net_io_counters(pernic=True).items())
    ]


def collect_snapshot() -> SystemSnapshot:
    now = time.time()
    boot = psutil.boot_time()
    return SystemSnapshot(
        hostname=socket.gethostname(),
        platform=f"{platform.system()} {platform.release()}",
        boot_time=boot,
        uptime_seconds=round(now - boot, 1),
        collected_at=now,
        cpu=collect_cpu(),
        memory=collect_memory(),
        disks=collect_disks(),
        network=collect_network(),
    )
