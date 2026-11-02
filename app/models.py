from pydantic import BaseModel, Field


class CpuInfo(BaseModel):
    percent: float = Field(description="Total CPU usage since the previous sample, 0-100")
    per_core: list[float]
    count_logical: int
    count_physical: int | None
    load_avg: list[float] | None = Field(description="1, 5 and 15 minute load average")


class MemoryInfo(BaseModel):
    total: int
    available: int
    used: int
    percent: float
    swap_total: int
    swap_used: int
    swap_percent: float


class DiskInfo(BaseModel):
    mountpoint: str
    fstype: str
    total: int
    used: int
    free: int
    percent: float


class NetworkInfo(BaseModel):
    interface: str
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int
    errin: int
    errout: int


class SystemSnapshot(BaseModel):
    hostname: str
    platform: str
    boot_time: float
    uptime_seconds: float
    collected_at: float
    cpu: CpuInfo
    memory: MemoryInfo
    disks: list[DiskInfo]
    network: list[NetworkInfo]


class ServiceStatus(BaseModel):
    name: str
    target: str
    up: bool
    latency_ms: float | None
    error: str | None


class ServicesReport(BaseModel):
    status: str = Field(description="ok when every service is up, degraded otherwise")
    services: list[ServiceStatus]
