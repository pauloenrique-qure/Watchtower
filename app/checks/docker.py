from __future__ import annotations
from app.models import DockerResult, ContainerInfo, Status, GatewayConfig
from app.teleport.adapter import TeleportAdapter, TeleportError

CORE_CONTAINERS = {"dicom_server", "web_server", "postgres_dcmio"}


_DOCKER_PS = 'docker ps --format "{{.Names}}|{{.Status}}|{{.Ports}}"'


def run(gw: GatewayConfig, teleport: TeleportAdapter) -> DockerResult:
    result = DockerResult()
    raw, error = _try_docker_ps(gw, teleport)

    if raw is None:
        result.status = Status.CRITICAL
        result.error = error
        return result

    result.containers = _parse_containers(raw)
    _classify_containers(result)
    result.status = _compute_status(result)
    return result


def _try_docker_ps(gw: GatewayConfig, teleport: TeleportAdapter) -> tuple[str | None, str]:
    """Try sudo docker first, fall back to docker without sudo."""
    last_error = ""
    for cmd in (f"sudo {_DOCKER_PS}", _DOCKER_PS):
        try:
            return teleport.ssh(gw.host, gw.ssh_login, cmd), ""
        except TeleportError as e:
            last_error = str(e)
    return None, f"docker not accessible ({last_error[:120]})"


def _parse_containers(output: str) -> list[ContainerInfo]:
    containers = []
    for line in output.strip().splitlines():
        parts = line.split("|", 2)
        if len(parts) < 2:
            continue
        name = parts[0].strip()
        status = parts[1].strip()
        ports = parts[2].strip() if len(parts) > 2 else ""
        containers.append(ContainerInfo(
            name=name,
            status=status,
            ports=ports,
            is_up="Up" in status,
            role=_classify_role(name),
        ))
    return containers


def _classify_role(name: str) -> str:
    if name in CORE_CONTAINERS:
        return "core"
    if name.startswith("worker"):
        return "worker"
    if "mirth" in name.lower():
        return "mirth"
    return "other"


def _classify_containers(result: DockerResult) -> None:
    workers = [c for c in result.containers if c.role == "worker"]
    mirth_containers = [c for c in result.containers if c.role == "mirth"]

    result.workers_total = len(workers)
    result.workers_up = sum(1 for c in workers if c.is_up)
    result.mirth_present = len(mirth_containers) > 0

    if result.mirth_present:
        all_mirth_up = all(c.is_up for c in mirth_containers)
        result.mirth_status = Status.OK if all_mirth_up else Status.WARNING
    else:
        result.mirth_status = Status.UNKNOWN

    if result.workers_total == 0:
        result.workers_status = Status.CRITICAL
    elif result.workers_up == 0:
        result.workers_status = Status.CRITICAL
    elif result.workers_up < result.workers_total:
        result.workers_status = Status.WARNING
    else:
        result.workers_status = Status.OK


def _compute_status(result: DockerResult) -> Status:
    container_map = {c.name: c for c in result.containers}

    missing_core = [name for name in CORE_CONTAINERS if name not in container_map]
    down_core = [
        name for name in CORE_CONTAINERS
        if name in container_map and not container_map[name].is_up
    ]

    if missing_core or down_core:
        result.core_status = Status.CRITICAL
        return Status.CRITICAL

    result.core_status = Status.OK

    if result.workers_status == Status.CRITICAL:
        return Status.CRITICAL
    if result.workers_status == Status.WARNING:
        return Status.WARNING
    if result.mirth_present and result.mirth_status == Status.WARNING:
        return Status.WARNING

    return Status.OK
