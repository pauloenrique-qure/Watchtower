from __future__ import annotations
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class Status(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"
    SKIPPED = "SKIPPED"


class GatewayConfig(BaseModel):
    name: str
    host: str
    ssh_login: str
    enabled: bool = True
    country: str = ""
    profile: str = "standard"


class AppConfig(BaseModel):
    check_interval_seconds: int = 120
    ssh_connection_timeout: int = 10
    remote_command_timeout: int = 30
    gateway_max_timeout: int = 60


class ContainerInfo(BaseModel):
    name: str
    status: str
    ports: str = ""
    is_up: bool = False
    role: str = "other"  # core | worker | mirth | other


class HardwareResult(BaseModel):
    status: Status = Status.UNKNOWN
    hostname: str = ""
    uptime: str = ""
    load_1m: float | None = None
    load_5m: float | None = None
    load_15m: float | None = None
    cores: int | None = None
    ram_total_mb: int | None = None
    ram_available_mb: int | None = None
    ram_used_pct: float | None = None
    swap_total_mb: int | None = None
    swap_used_mb: int | None = None
    swap_used_pct: float | None = None
    disk_used_pct: float | None = None
    disk_available: str = ""
    temp_celsius: float | None = None
    throttled: str = "UNKNOWN"
    error: str = ""


class DockerResult(BaseModel):
    status: Status = Status.UNKNOWN
    containers: list[ContainerInfo] = Field(default_factory=list)
    core_status: Status = Status.UNKNOWN
    workers_up: int = 0
    workers_total: int = 0
    workers_status: Status = Status.UNKNOWN
    mirth_present: bool = False
    mirth_status: Status = Status.UNKNOWN
    error: str = ""


class PipelineSummary(BaseModel):
    last_successful_task_at: str | None = None
    last_image_created_at: str | None = None
    last_image_updated_at: str | None = None
    not_uploaded_to_cloud: int | None = None
    images_last_5m: int | None = None
    images_last_15m: int | None = None
    images_updated_last_5m: int | None = None
    pending_created_15m: int | None = None
    processed_15m: int | None = None
    failed_15m: int | None = None
    pending_total: int | None = None
    pending_older_30m: int | None = None
    pending_older_2h: int | None = None
    backlog_by_type: list[dict[str, Any]] = Field(default_factory=list)
    failed_by_type: list[dict[str, Any]] = Field(default_factory=list)
    failed_last_24h: list[dict[str, Any]] = Field(default_factory=list)
    processed_by_type_15m: list[dict[str, Any]] = Field(default_factory=list)
    task_status_counts: list[dict[str, Any]] = Field(default_factory=list)
    study_processing_status: list[dict[str, Any]] = Field(default_factory=list)
    series_processing_status: list[dict[str, Any]] = Field(default_factory=list)


class PostgresResult(BaseModel):
    status: Status = Status.UNKNOWN
    reachable: bool = False
    error: str = ""


class PipelineResult(BaseModel):
    status: Status = Status.UNKNOWN
    summary: PipelineSummary = Field(default_factory=PipelineSummary)
    error: str = ""


class MirthResult(BaseModel):
    status: Status = Status.UNKNOWN
    present: bool = False
    containers: list[ContainerInfo] = Field(default_factory=list)
    error: str = ""


class GatewaySnapshot(BaseModel):
    gateway_host: str
    gateway_name: str
    timestamp: str
    overall_status: Status
    health_score: int
    ssh_status: Status
    docker_status: Status
    postgres_status: Status
    pipeline_status: Status
    hardware_status: Status
    mirth_status: Status
    hardware: HardwareResult | None = None
    docker: DockerResult | None = None
    postgres: PostgresResult | None = None
    pipeline: PipelineResult | None = None
    mirth: MirthResult | None = None
    error_message: str = ""


class SchedulerState(BaseModel):
    running: bool = True
    last_run: str | None = None
    next_run: str | None = None
    in_progress: bool = False
