from __future__ import annotations
from app.models import MirthResult, Status, GatewayConfig, DockerResult
from app.teleport.adapter import TeleportAdapter


def run(docker_result: DockerResult) -> MirthResult:
    result = MirthResult()
    mirth_containers = [c for c in docker_result.containers if c.role == "mirth"]

    result.present = len(mirth_containers) > 0
    result.containers = mirth_containers

    if not result.present:
        result.status = Status.UNKNOWN
        return result

    all_up = all(c.is_up for c in mirth_containers)
    result.status = Status.OK if all_up else Status.WARNING
    return result
