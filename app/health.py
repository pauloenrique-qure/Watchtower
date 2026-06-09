from __future__ import annotations
from app.models import (
    GatewaySnapshot, Status,
    HardwareResult, DockerResult, PostgresResult, PipelineResult, MirthResult,
)

_WEIGHTS = {
    "ssh": 25,
    "docker_core": 20,
    "postgres": 15,
    "workers": 10,
    "pipeline": 15,
    "hardware": 10,
    "mirth": 5,
}

_STATUS_SCORE = {
    Status.OK: 1.0,
    Status.WARNING: 0.5,
    Status.UNKNOWN: 0.5,
    Status.SKIPPED: 0.0,
    Status.CRITICAL: 0.0,
}


def compute_score(
    ssh_status: Status,
    docker: DockerResult | None,
    postgres: PostgresResult | None,
    pipeline: PipelineResult | None,
    hardware: HardwareResult | None,
    mirth_present: bool,
) -> int:
    if ssh_status != Status.OK:
        return 0

    docker_core = docker.core_status if docker else Status.UNKNOWN
    workers = docker.workers_status if docker else Status.UNKNOWN
    mirth = (docker.mirth_status if docker else Status.UNKNOWN) if mirth_present else None

    if docker_core == Status.CRITICAL:
        cap = 50
    elif postgres and postgres.status == Status.CRITICAL:
        cap = 60
    else:
        cap = 100

    total_weight = sum(_WEIGHTS[k] for k in _WEIGHTS if k != "mirth")
    if mirth_present:
        total_weight += _WEIGHTS["mirth"]

    raw = 0.0
    raw += _WEIGHTS["ssh"] * _STATUS_SCORE[ssh_status]
    raw += _WEIGHTS["docker_core"] * _STATUS_SCORE[docker_core]
    raw += _WEIGHTS["postgres"] * _STATUS_SCORE[postgres.status if postgres else Status.UNKNOWN]
    raw += _WEIGHTS["workers"] * _STATUS_SCORE[workers]
    raw += _WEIGHTS["pipeline"] * _STATUS_SCORE[pipeline.status if pipeline else Status.UNKNOWN]
    raw += _WEIGHTS["hardware"] * _STATUS_SCORE[hardware.status if hardware else Status.UNKNOWN]

    if mirth_present and mirth is not None:
        raw += _WEIGHTS["mirth"] * _STATUS_SCORE[mirth]

    score = int((raw / total_weight) * 100)
    return min(score, cap)


def compute_overall_status(snapshot: GatewaySnapshot) -> Status:
    if snapshot.ssh_status != Status.OK:
        return Status.CRITICAL

    statuses = [
        snapshot.docker_status,
        snapshot.postgres_status,
        snapshot.pipeline_status,
        snapshot.hardware_status,
    ]
    if snapshot.mirth_status not in (Status.UNKNOWN, Status.SKIPPED):
        statuses.append(snapshot.mirth_status)

    if Status.CRITICAL in statuses:
        return Status.CRITICAL
    if Status.WARNING in statuses:
        return Status.WARNING
    if all(s == Status.OK for s in statuses):
        return Status.OK
    return Status.UNKNOWN
