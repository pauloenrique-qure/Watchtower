from __future__ import annotations
from app.models import PostgresResult, Status, GatewayConfig
from app.teleport.adapter import TeleportAdapter, TeleportError

_PSQL_SUDO = "sudo docker exec -i postgres_dcmio psql -U postgres -d dcmio -t -A -F '|'"
_PSQL_NOSU = "docker exec -i postgres_dcmio psql -U postgres -d dcmio -t -A -F '|'"
_PROBE_QUERY = "SELECT 1"

# Per-host cache: once we know which command works, reuse it.
_cmd_cache: dict[str, str] = {}


def run(gw: GatewayConfig, teleport: TeleportAdapter) -> PostgresResult:
    result = PostgresResult()
    try:
        output = psql(gw, teleport, _PROBE_QUERY)
        result.reachable = "1" in output.strip()
        result.status = Status.OK if result.reachable else Status.CRITICAL
    except TeleportError as e:
        result.status = Status.CRITICAL
        result.error = str(e)
    return result


def psql(gw: GatewayConfig, teleport: TeleportAdapter, query: str) -> str:
    safe = query.replace("'", "'\\''")
    base = _resolve_cmd(gw, teleport)
    cmd = f"{base} -c '{safe}'"
    return teleport.ssh(gw.host, gw.ssh_login, cmd)


def psql_raw(gw: GatewayConfig, teleport: TeleportAdapter, sql_block: str) -> str:
    escaped = sql_block.replace("'", "'\\''")
    base = _resolve_cmd(gw, teleport)
    cmd = f"echo '{escaped}' | {base}"
    return teleport.ssh(gw.host, gw.ssh_login, cmd)


def _resolve_cmd(gw: GatewayConfig, teleport: TeleportAdapter) -> str:
    """Return the working psql base command for this host, caching the result."""
    if gw.host in _cmd_cache:
        return _cmd_cache[gw.host]

    for candidate in (_PSQL_NOSU, _PSQL_SUDO):
        try:
            safe = _PROBE_QUERY.replace("'", "'\\''")
            out = teleport.ssh(gw.host, gw.ssh_login, f"{candidate} -c '{safe}'")
            if "1" in out:
                _cmd_cache[gw.host] = candidate
                return candidate
        except TeleportError:
            continue

    # Neither worked — default to sudo so the error message is descriptive
    _cmd_cache[gw.host] = _PSQL_SUDO
    return _PSQL_SUDO
