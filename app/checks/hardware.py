from __future__ import annotations
import re
from app.models import HardwareResult, Status, GatewayConfig
from app.teleport.adapter import TeleportAdapter, TeleportError
from app.teleport.commands import HARDWARE_BATCH as _BATCH_SCRIPT


def run(gw: GatewayConfig, teleport: TeleportAdapter) -> HardwareResult:
    result = HardwareResult()
    try:
        output = teleport.ssh(gw.host, gw.ssh_login, _BATCH_SCRIPT.strip())
        sections = _split_sections(output)
        result.hostname = sections.get("HOSTNAME", "").strip()
        result.uptime = sections.get("UPTIME", "").strip()
        result.uptime_short = _parse_uptime_short(result.uptime)
        _parse_loadavg(result, sections.get("LOADAVG", ""))
        _parse_cores(result, sections.get("NPROC", ""))
        _parse_memory(result, sections.get("MEMORY", ""))
        _parse_disk(result, sections.get("DISK", ""))
        _parse_temperature(result, sections.get("TEMP", ""))
        _parse_throttling(result, sections.get("THROTTLE", ""))
        result.status = _compute_status(result)
    except TeleportError as e:
        result.status = Status.CRITICAL
        result.error = str(e)
    return result


def _parse_uptime_short(uptime_str: str) -> str:
    match = re.search(r'up\s+(.*?),\s+\d+\s+user', uptime_str)
    if not match:
        return ""
    raw = match.group(1).strip()

    m = re.match(r'(\d+)\s+day', raw)
    if m:
        return f"↑ {m.group(1)}d"

    m = re.match(r'(\d+):(\d+)', raw)
    if m:
        h = int(m.group(1))
        return f"↑ {h}h" if h else f"↑ {m.group(2)}m"

    m = re.match(r'(\d+)\s+min', raw)
    if m:
        return f"↑ {m.group(1)}m"

    return f"↑ {raw}"


def _split_sections(output: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_key = None
    current_lines: list[str] = []

    for line in output.splitlines():
        if line.startswith("---") and line.endswith("---"):
            if current_key:
                sections[current_key] = "\n".join(current_lines)
            current_key = line.strip("-")
            current_lines = []
        else:
            current_lines.append(line)

    if current_key:
        sections[current_key] = "\n".join(current_lines)

    return sections


def _parse_loadavg(result: HardwareResult, output: str) -> None:
    parts = output.strip().split()
    if len(parts) >= 3:
        try:
            result.load_1m = float(parts[0])
            result.load_5m = float(parts[1])
            result.load_15m = float(parts[2])
        except ValueError:
            pass


def _parse_cores(result: HardwareResult, output: str) -> None:
    try:
        result.cores = int(output.strip())
    except ValueError:
        pass


def _parse_memory(result: HardwareResult, output: str) -> None:
    for line in output.splitlines():
        parts = line.split()
        if parts and parts[0] == "Mem:":
            try:
                result.ram_total_mb = int(parts[1])
                result.ram_available_mb = int(parts[6]) if len(parts) > 6 else int(parts[3])
                if result.ram_total_mb:
                    used = result.ram_total_mb - result.ram_available_mb
                    result.ram_used_pct = round(used / result.ram_total_mb * 100, 1)
            except (ValueError, IndexError):
                pass
        elif parts and parts[0] == "Swap:":
            try:
                result.swap_total_mb = int(parts[1])
                result.swap_used_mb = int(parts[2])
                if result.swap_total_mb:
                    result.swap_used_pct = round(result.swap_used_mb / result.swap_total_mb * 100, 1)
            except (ValueError, IndexError):
                pass


def _parse_disk(result: HardwareResult, output: str) -> None:
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[5] == "/":
            try:
                result.disk_used_pct = float(parts[4].replace("%", ""))
                result.disk_available = parts[3]
            except ValueError:
                pass
            break


def _parse_temperature(result: HardwareResult, output: str) -> None:
    raw = output.strip()
    if not raw or raw == "UNKNOWN":
        result.temp_celsius = None
        return
    try:
        # thermal_zone format: 54000
        result.temp_celsius = round(int(raw) / 1000, 1)
        return
    except ValueError:
        pass
    try:
        # vcgencmd format: temp=43.0'C
        value = raw.replace("temp=", "").replace("'C", "").strip()
        result.temp_celsius = float(value)
    except ValueError:
        result.temp_celsius = None


def _parse_throttling(result: HardwareResult, output: str) -> None:
    raw = output.strip()
    if not raw or raw == "UNKNOWN":
        result.throttled = "UNKNOWN"
        return
    try:
        value = raw.split("=")[-1].strip()
        throttled_int = int(value, 16)
        result.throttled = "THROTTLED" if throttled_int != 0 else "OK"
    except ValueError:
        result.throttled = "UNKNOWN"


def _compute_status(r: HardwareResult) -> Status:
    statuses = []

    if r.load_5m is not None and r.cores:
        if r.load_5m > r.cores * 2:
            statuses.append(Status.CRITICAL)
        elif r.load_5m > r.cores:
            statuses.append(Status.WARNING)

    if r.disk_used_pct is not None:
        if r.disk_used_pct > 95:
            statuses.append(Status.CRITICAL)
        elif r.disk_used_pct > 85:
            statuses.append(Status.WARNING)

    if r.ram_total_mb and r.ram_available_mb is not None:
        avail_pct = r.ram_available_mb / r.ram_total_mb * 100
        if avail_pct < 5:
            statuses.append(Status.CRITICAL)
        elif avail_pct < 15:
            statuses.append(Status.WARNING)

    if r.swap_used_pct is not None and r.swap_used_pct > 80:
        statuses.append(Status.WARNING)

    if r.temp_celsius is not None:
        if r.temp_celsius >= 80:
            statuses.append(Status.CRITICAL)
        elif r.temp_celsius >= 70:
            statuses.append(Status.WARNING)

    if r.throttled == "THROTTLED":
        statuses.append(Status.WARNING)

    if not statuses:
        return Status.OK
    if Status.CRITICAL in statuses:
        return Status.CRITICAL
    if Status.WARNING in statuses:
        return Status.WARNING
    return Status.OK
