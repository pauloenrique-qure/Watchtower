from __future__ import annotations
import base64

# _issued is the single source of truth: a command may only reach the adapter
# if it was registered here. Constants are registered at import time via _r().
# There is no generic SQL builder — each allowed operation has its own named
# constant or builder that produces only pre-approved command strings.
_issued: set[str] = set()


def _r(cmd: str) -> str:
    _issued.add(cmd)
    return cmd


# ── SSH probe ──────────────────────────────────────────────────────────────
SSH_PROBE = _r("hostname")

# ── Hardware ───────────────────────────────────────────────────────────────
HARDWARE_BATCH = _r(
    "echo '---HOSTNAME---'\n"
    "hostname\n"
    "echo '---UPTIME---'\n"
    "uptime\n"
    "echo '---LOADAVG---'\n"
    "cat /proc/loadavg\n"
    "echo '---NPROC---'\n"
    "nproc\n"
    "echo '---MEMORY---'\n"
    "free -m\n"
    "echo '---DISK---'\n"
    "df -h /\n"
    "echo '---TEMP---'\n"
    "cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || vcgencmd measure_temp 2>/dev/null || echo 'UNKNOWN'\n"
    "echo '---THROTTLE---'\n"
    "vcgencmd get_throttled 2>/dev/null || echo 'UNKNOWN'"
)

# ── Docker ─────────────────────────────────────────────────────────────────
DOCKER_PS = _r('docker ps --format "{{.Names}}|{{.Status}}|{{.Ports}}"')
DOCKER_PS_SUDO = _r(f"sudo {DOCKER_PS}")

# ── PostgreSQL ─────────────────────────────────────────────────────────────
PSQL_BASE = "docker exec -i postgres_dcmio psql -U postgres -d dcmio -t -A -F '|'"
PSQL_BASE_SUDO = f"sudo {PSQL_BASE}"

# Connectivity probe — the only direct psql command allowed.
PSQL_PROBE_CMD = _r(f"{PSQL_BASE} -c 'SELECT 1'")
PSQL_PROBE_CMD_SUDO = _r(f"{PSQL_BASE_SUDO} -c 'SELECT 1'")

_PSQL_BASES = frozenset({PSQL_BASE, PSQL_BASE_SUDO})

# ── Pipeline batch ─────────────────────────────────────────────────────────
# The SQL is owned here and transmitted via base64 so there is no shell
# quoting surface. There is no generic SQL builder — to add a new query,
# add it here and update the corresponding parser in pipeline.py.
_PIPELINE_BATCH_SQL = (
    "SELECT '---LAST_TASK---';\n"
    "SELECT MAX(processed_at) FROM job_manager_task WHERE status = 2;\n"
    "\n"
    "SELECT '---IMAGE_SUMMARY---';\n"
    "SELECT MAX(created_at), MAX(updated_at),\n"
    "  COUNT(*) FILTER (WHERE is_uploaded_to_cloud = false)\n"
    "FROM image_manager_image;\n"
    "\n"
    "SELECT '---IMAGES_RECENT---';\n"
    "SELECT\n"
    "  COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '5 minutes'),\n"
    "  COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '15 minutes'),\n"
    "  COUNT(*) FILTER (WHERE updated_at >= NOW() - INTERVAL '5 minutes'),\n"
    "  COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours')\n"
    "FROM image_manager_image;\n"
    "\n"
    "SELECT '---TASKS_RECENT---';\n"
    "SELECT\n"
    "  COUNT(*) FILTER (WHERE status = 0 AND created_at >= NOW() - INTERVAL '15 minutes'),\n"
    "  COUNT(*) FILTER (WHERE status = 2 AND processed_at >= NOW() - INTERVAL '15 minutes'),\n"
    "  COUNT(*) FILTER (WHERE status = -1 AND updated_at >= NOW() - INTERVAL '15 minutes')\n"
    "FROM job_manager_task;\n"
    "\n"
    "SELECT '---BACKLOG---';\n"
    "SELECT\n"
    "  COUNT(*) FILTER (WHERE status = 0),\n"
    "  COUNT(*) FILTER (WHERE status = 0 AND created_at < NOW() - INTERVAL '30 minutes'),\n"
    "  COUNT(*) FILTER (WHERE status = 0 AND created_at < NOW() - INTERVAL '2 hours')\n"
    "FROM job_manager_task;\n"
    "\n"
    "SELECT '---BACKLOG_BY_TYPE---';\n"
    "SELECT type, COUNT(*), MIN(created_at), MAX(updated_at)\n"
    "FROM job_manager_task WHERE status = 0\n"
    "GROUP BY type ORDER BY COUNT(*) DESC LIMIT 10;\n"
    "\n"
    "SELECT '---FAILED_BY_TYPE---';\n"
    "SELECT type, COUNT(*), MAX(updated_at)\n"
    "FROM job_manager_task WHERE status = -1\n"
    "GROUP BY type ORDER BY COUNT(*) DESC LIMIT 10;\n"
    "\n"
    "SELECT '---FAILED_24H---';\n"
    "SELECT type, COUNT(*), MAX(updated_at)\n"
    "FROM job_manager_task WHERE status = -1\n"
    "  AND updated_at >= NOW() - INTERVAL '24 hours'\n"
    "GROUP BY type ORDER BY COUNT(*) DESC;\n"
    "\n"
    "SELECT '---PROCESSED_15M---';\n"
    "SELECT type, COUNT(*), MAX(processed_at)\n"
    "FROM job_manager_task WHERE status = 2\n"
    "  AND processed_at >= NOW() - INTERVAL '15 minutes'\n"
    "GROUP BY type ORDER BY COUNT(*) DESC;\n"
    "\n"
    "SELECT '---TASK_STATUS_COUNTS---';\n"
    "SELECT status, COUNT(*) FROM job_manager_task GROUP BY status ORDER BY status;\n"
    "\n"
    "SELECT '---STUDY_STATUS---';\n"
    "SELECT processing_status, COUNT(*)\n"
    "FROM image_manager_imagestudy GROUP BY processing_status ORDER BY processing_status;\n"
    "\n"
    "SELECT '---SERIES_STATUS---';\n"
    "SELECT processing_status, COUNT(*)\n"
    "FROM image_manager_imageseries GROUP BY processing_status ORDER BY processing_status;\n"
    "\n"
    "SELECT '---SC_PUBLISH_24H---';\n"
    "SELECT COUNT(*)\n"
    "FROM job_manager_task\n"
    "WHERE status = 2\n"
    "  AND type = 'workflow_manager.publishing.publishers.dicom_publisher.DicomPublisher:publish'\n"
    "  AND processed_at >= NOW() - INTERVAL '24 hours';\n"
)

_PIPELINE_B64 = base64.b64encode(_PIPELINE_BATCH_SQL.encode()).decode()
_PIPELINE_BATCH_CMD = _r(f"echo {_PIPELINE_B64} | base64 -d | {PSQL_BASE}")
_PIPELINE_BATCH_CMD_SUDO = _r(f"echo {_PIPELINE_B64} | base64 -d | {PSQL_BASE_SUDO}")


def build_pipeline_batch(base: str) -> str:
    """Return the pre-registered pipeline batch command for the given psql base."""
    if base == PSQL_BASE:
        return _PIPELINE_BATCH_CMD
    if base == PSQL_BASE_SUDO:
        return _PIPELINE_BATCH_CMD_SUDO
    raise ValueError(f"Unknown psql base command: {base!r}")


def validate(cmd: str) -> None:
    """Raise ValueError if cmd was not registered in the read-only allowlist."""
    if cmd in _issued:
        return
    raise ValueError(f"Remote command not in read-only allowlist: {cmd[:80]!r}")
