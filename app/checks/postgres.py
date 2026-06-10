from __future__ import annotations
from app.models import PostgresResult, Status, GatewayConfig
from app.teleport.adapter import TeleportAdapter, TeleportError
from app.teleport import commands

_PROBE_QUERY = "SELECT 1"

# Per-host cache: once we know which base command works, reuse it.
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
    if query != _PROBE_QUERY:
        raise ValueError("psql() only runs the connectivity probe — use run_batch() for batch SQL")
    base = _resolve_cmd(gw, teleport)
    cmd = commands.PSQL_PROBE_CMD if base == commands.PSQL_BASE else commands.PSQL_PROBE_CMD_SUDO
    try:
        return teleport.ssh(gw.host, gw.ssh_login, cmd)
    except TeleportError:
        _cmd_cache.pop(gw.host, None)
        raise


def run_batch(gw: GatewayConfig, teleport: TeleportAdapter) -> str:
    """Execute the pre-approved pipeline batch SQL and return raw psql output."""
    base = _resolve_cmd(gw, teleport)
    cmd = commands.build_pipeline_batch(base)
    try:
        return teleport.ssh(gw.host, gw.ssh_login, cmd)
    except TeleportError:
        _cmd_cache.pop(gw.host, None)
        raise


def _resolve_cmd(gw: GatewayConfig, teleport: TeleportAdapter) -> str:
    """Return the working psql base command for this host, caching the result."""
    if gw.host in _cmd_cache:
        return _cmd_cache[gw.host]

    for probe_cmd, base in (
        (commands.PSQL_PROBE_CMD, commands.PSQL_BASE),
        (commands.PSQL_PROBE_CMD_SUDO, commands.PSQL_BASE_SUDO),
    ):
        try:
            out = teleport.ssh(gw.host, gw.ssh_login, probe_cmd)
            if "1" in out:
                _cmd_cache[gw.host] = base
                return base
        except TeleportError:
            continue

    # Neither worked — default to sudo so the error message is descriptive
    _cmd_cache[gw.host] = commands.PSQL_BASE_SUDO
    return commands.PSQL_BASE_SUDO
